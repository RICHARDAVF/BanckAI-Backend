from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR
from core.utils.ModelsApi import Model
from difflib import SequenceMatcher
from django.conf import settings
import json
from django.core.cache import cache
import os
import pandas as pd
from .models import Chat, Message
from rest_framework.permissions import IsAuthenticated
from core.middleware import CookieJWTAuthentication
from rest_framework.generics import ListAPIView,CreateAPIView,DestroyAPIView
from .serializer import ChatSerializer, MessageSerializer
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

class IntentType(Enum):
    CONVERSATION = "conversation"
    REPORT_REQUEST = "report_request"
    REPORT_FILTER = "report_filter"
    CLIENT_INFO = "client_info"

@dataclass
class ParsedIntent:
    intent_type: IntentType
    confidence: float
    entities: Dict[str, Any]
    response_text: Optional[str] = None

class DataManager:
    @staticmethod
    def get_dataframe(file_path, sheet_name="DETALLE", cache_timeout=3600):
        cache_key = f"excel_data_{hash(str(file_path))}_{sheet_name}"
        df = cache.get(cache_key)
        if df is not None:
            return df
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            cache.set(cache_key, df, timeout=cache_timeout)
            return df
        except Exception as e:
            raise ValueError(f"Error al leer archivo Excel: {str(e)}")

class ClientMatcher:
    @staticmethod
    def find_best_client_match(search_text, client_list):
        if not client_list:
            return None
        best_score = 0
        best_client = None
        for client in client_list:
            if pd.isna(client):
                continue
            score = SequenceMatcher(None, search_text.lower(), str(client).lower()).ratio()
            if score > best_score:
                best_score = score
                best_client = client
        return best_client if best_score > 0.3 else None

class ReportingService:
    def __init__(self, excel_file_path=None):
        self.excel_file_path = excel_file_path or self._get_default_path()
        self.data_manager = DataManager()
        self.client_matcher = ClientMatcher()
    
    def _get_default_path(self):
        return settings.MEDIA_ROOT / "xlsx/Run Off BEC 202505_ejecutado 2904 - CARLOS RONCEROS VILCHEZ.xlsx"
    
    def get_dataset(self):
        return self.data_manager.get_dataframe(self.excel_file_path)
    
    def get_client_list(self):
        df: pd.DataFrame = self.get_dataset()
        if "Empresa" not in df.columns:
            raise ValueError('Columna empresa no encontrada')
        return df["Empresa"].dropna().unique().tolist()
    
    def find_client_by_text(self, search_text):
        clients = self.get_client_list()
        return self.client_matcher.find_best_client_match(search_text, clients)

    def get_filtered_data(self, client_name=None, product=None, date_from=None, date_to=None):
        """Filtra los datos según múltiples criterios"""
        df = self.get_dataset()
        
        if client_name:
            df = df[df["Empresa"] == client_name]
        if product:
            df = df[df["Producto"] == product] if "Producto" in df.columns else df
        
        return df[["Empresa","Fecha Venc.Cuota","Producto","Capital","Capital L/P","Capital Divisa","Fecha Vencimiento","weekmonth"]]

class IntentParser:
    """Clase que maneja la interpretación de intenciones usando IA"""
    
    def __init__(self):
        self.reporting_service = ReportingService()
    
    def parse_user_intent(self, user_message: str, conversation_history: List[Dict] = None) -> ParsedIntent:
        """
        Analiza el mensaje del usuario y determina la intención
        """
        context = self._build_context(conversation_history) if conversation_history else ""
        available_clients = self.reporting_service.get_client_list()[:10]  # Primeros 10 para no saturar
        
        prompt = f"""
Eres un asistente inteligente que ayuda con reportes empresariales y conversación general.

CONTEXTO DE CONVERSACIÓN PREVIA:
{context}

CLIENTES DISPONIBLES (algunos ejemplos):
{', '.join(available_clients)}

MENSAJE DEL USUARIO: "{user_message}"

Analiza el mensaje y determina la intención. Responde ÚNICAMENTE con un JSON válido siguiendo esta estructura:

{{
    "intent_type": "conversation|report_request|report_filter|client_info",
    "confidence": 0.0-1.0,
    "entities": {{
        "client_name": "nombre del cliente si se menciona",
        "product": "tipo de producto si se menciona (LEASING, COMERCIAL, FIANZAS, etc.)",
        "date_from": "fecha inicial si se menciona",
        "date_to": "fecha final si se menciona",
        "filters": ["lista de filtros mencionados"]
    }},
    "response_text": "respuesta natural para conversación normal, null para reportes"
}}

REGLAS:
- "conversation": Para saludos, preguntas generales, charla casual, informacion de ultimos reportes que esten en el chat
- "report_request": Para solicitudes específicas de reportes o datos
- "report_filter": Para filtrar/modificar reportes existentes
- "client_info": Para información específica sobre un cliente
- Si mencionan un cliente, busca el más similar en la lista disponible
- Para conversación normal, incluye response_text con una respuesta natural
- Para reportes, response_text debe ser null
"""

        try:
            response = Model.gemini(prompt=prompt, modelname="gemini-1.5-flash")
            # Limpiar respuesta por si tiene markdown
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:-3]
            elif clean_response.startswith('```'):
                clean_response = clean_response[3:-3]
            
            parsed_data = json.loads(clean_response)
            
            # Validar y corregir nombres de clientes
            if parsed_data.get("entities", {}).get("client_name"):
                best_match = self.reporting_service.find_client_by_text(
                    parsed_data["entities"]["client_name"]
                )
                if best_match:
                    parsed_data["entities"]["client_name"] = best_match
            
            return ParsedIntent(
                intent_type=IntentType(parsed_data["intent_type"]),
                confidence=parsed_data["confidence"],
                entities=parsed_data["entities"],
                response_text=parsed_data.get("response_text")
            )
            
        except Exception as e:
            # Fallback: interpretación básica
            return self._fallback_intent_parsing(user_message)
    
    def _build_context(self, conversation_history: List[Dict]) -> str:
        """Construye el contexto de conversación"""
        if not conversation_history:
            return ""
        
        context_lines = []
        for msg in conversation_history[-5:]:  # Últimos 5 mensajes
            sender = msg.get('sender', 'unknown')
            text = msg.get('message_text', '')
            context_lines.append(f"{sender}: {text}")
        
        return "\n".join(context_lines)
    
    def _fallback_intent_parsing(self, user_message: str) -> ParsedIntent:
        """Análisis básico de intención como fallback"""
        message_lower = user_message.lower()
        
        # Palabras clave para reportes
        report_keywords = ['reporte', 'informe', 'datos', 'mostrar', 'ver', 'generar', 'cliente']
        conversation_keywords = ['hola', 'gracias', 'cómo', 'qué tal', 'ayuda']
        
        if any(keyword in message_lower for keyword in report_keywords):
            return ParsedIntent(
                intent_type=IntentType.REPORT_REQUEST,
                confidence=0.6,
                entities={},
                response_text=None
            )
        else:
            return ParsedIntent(
                intent_type=IntentType.CONVERSATION,
                confidence=0.7,
                entities={},
                response_text="Entiendo, ¿en qué más puedo ayudarte?"
            )

class ReportGenerator:
    """Clase especializada en generar reportes"""
    
    def __init__(self, reporting_service: ReportingService):
        self.reporting_service = reporting_service
    
    def generate_report(self, intent: ParsedIntent) -> Dict[str, Any]:
        """Genera reporte basado en la intención parseada"""
        entities = intent.entities
        
        client_name = entities.get("client_name")
        product = entities.get("product")
        
        if not client_name:
            return {
                "success": False,
                "error": "No se pudo identificar el cliente para el reporte",
                "suggestion": "Por favor, especifica el nombre del cliente"
            }
        
        try:
            # Obtener datos filtrados
            filtered_data = self.reporting_service.get_filtered_data(
                client_name=client_name,
                product=product
            )
            
            if filtered_data.empty:
                return {
                    "success": False,
                    "error": f"No se encontraron datos para el cliente: {client_name}",
                    "available_clients": self.reporting_service.get_client_list()[:5]
                }
            
            # Generar tabla HTML
            html_table = self._format_as_html_table(filtered_data)
            
            # Generar resumen con IA
            summary = self._generate_summary(filtered_data, entities)
            
            return {
                "success": True,
                "data": {
                    "html_table": html_table,
                    "summary": summary,
                    "client_name": client_name,
                    "total_records": len(filtered_data),
                    "filters_applied": entities
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error generando reporte: {str(e)}"
            }
    
    def _format_as_html_table(self, df: pd.DataFrame) -> str:
        """Formatea DataFrame como tabla HTML"""
        if df.empty:
            return "<p>No se encontraron datos para mostrar.</p>"
        
        return df.to_html(
            index=False,
            classes='table table-striped table-bordered',
            escape=False,
            float_format='{:.2f}'.format
        )
    
    def _generate_summary(self, df: pd.DataFrame, entities: Dict) -> str:
        """Genera un resumen inteligente de los datos"""
        try:
            stats = {
                "total_records": len(df),
                "products": df["Producto"].unique().tolist() if "Producto" in df.columns else [],
                "client": entities.get("client_name", "N/A")
            }
            
            prompt = f"""
Genera un resumen ejecutivo breve y profesional basado en estos datos:

Cliente: {stats['client']}
Total de registros: {stats['total_records']}
Productos: {', '.join(stats['products']) if stats['products'] else 'No especificados'}

El resumen debe ser conciso (2-3 oraciones) y orientado a negocio.
"""
            
            summary = Model.gemini(prompt=prompt, modelname="gemini-1.5-flash")
            return summary.strip()
            
        except Exception:
            return f"Reporte generado para {entities.get('client_name', 'cliente')} con {len(df)} registros encontrados."

class ChatMessageCreateView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]
    
    def post(self, request, *args, **kwargs):
        try:
            user = request.user
            text = request.data["message_text"]
            chat_id = request.data.get("chat_id")
            # Obtener o crear chat
            if chat_id:
                chat = Chat.objects.get(pk=chat_id, user=user)
            else:
                chat = Chat.objects.create(user=user, title=f"{text[:50]}")
            conversation_history = list(
                Message.objects.filter(chat=chat)
                .order_by('-created_at')[:10]
                .values('sender', 'message_text')
            )
            # Parsear intención
            intent_parser = IntentParser()
            print(conversation_history,123123)
            intent = intent_parser.parse_user_intent(text, conversation_history)
            print(intent)
            response_data = self._process_intent(intent)
            ai_response_text = self._extract_response_text(response_data, intent)
            instance = Message.objects.create(chat=chat, sender="ai", message_text=ai_response_text)
            data = {
                "data" :instance.toJSON(),
                "success":True
            }
            return Response(data=data, status=HTTP_200_OK)
            
        except Exception as e:
            return Response(data={
                "error": str(e),
                "success": False
            }, status=HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _process_intent(self, intent: ParsedIntent) -> Dict[str, Any]:
        """Procesa la intención y retorna la respuesta apropiada"""
        
        if intent.intent_type == IntentType.CONVERSATION:
            return {
                "success": True,
                "type": "conversation",
                "data": intent.response_text or "¿En qué puedo ayudarte hoy?"
            }
        
        elif intent.intent_type in [IntentType.REPORT_REQUEST, IntentType.REPORT_FILTER]:
            reporting_service = ReportingService()
            report_generator = ReportGenerator(reporting_service)
            report_result = report_generator.generate_report(intent)
            
            return {
                "success": report_result["success"],
                "type": "report",
                "data": report_result.get("data"),
                "error": report_result.get("error"),
                "suggestion": report_result.get("suggestion"),
                "available_clients": report_result.get("available_clients")
            }
        
        elif intent.intent_type == IntentType.CLIENT_INFO:
            return self._handle_client_info(intent)
        
        else:
            return {
                "success": True,
                "type": "conversation",
                "data": "No estoy seguro de cómo ayudarte con eso. ¿Podrías ser más específico?"
            }
    
    def _handle_client_info(self, intent: ParsedIntent) -> Dict[str, Any]:
        """Maneja solicitudes de información específica del cliente"""
        client_name = intent.entities.get("client_name")
        
        if not client_name:
            return {
                "success": False,
                "type": "conversation",
                "data": "¿Sobre qué cliente te gustaría obtener información?"
            }
        
        try:
            reporting_service = ReportingService()
            client_data = reporting_service.get_filtered_data(client_name=client_name)
            
            if client_data.empty:
                return {
                    "success": False,
                    "type": "conversation",
                    "data": f"No encontré información para el cliente: {client_name}"
                }
            
            summary = {
                "client": client_name,
                "total_records": len(client_data),
                "products": client_data["Producto"].unique().tolist() if "Producto" in client_data.columns else []
            }
            
            return {
                "success": True,
                "type": "client_info",
                "data": summary
            }
            
        except Exception as e:
            return {
                "success": False,
                "type": "conversation",
                "data": f"Error obteniendo información del cliente: {str(e)}"
            }
    
    def _extract_response_text(self, response_data: Dict, intent: ParsedIntent) -> str:
        """Extrae el texto de respuesta para guardar en la BD"""

        if response_data.get("type") == "conversation":
            return response_data.get("data", "")

        elif response_data.get("type") == "report":
            if response_data.get("success"):
                summary = response_data["data"].get("summary", "")
                html_table = response_data["data"].get("html_table", "")
                client_name = intent.entities.get('client_name') or response_data["data"].get("client_name", "cliente")

                return f"""
                    <div>
                        <p><strong>Reporte generado para:</strong> {client_name}</p>
                        <p>{summary}</p>
                        <div style="overflow-x: auto; margin-top: 1em;">
                            {html_table}
                        </div>
                    </div>
                """
            else:
                return response_data.get("error", "Error generando reporte")

        else:
            return str(response_data.get("data", "Respuesta procesada"))

class ChatListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]
    serializer_class = ChatSerializer
    queryset = Chat.objects.all()
    def get(self,request,*args,**kwargs):
        try:
            queryset = self.get_queryset().filter(user=request.user)
            serializer = self.get_serializer(queryset,many=True)
            return Response(
                data={
                    "data":serializer.data,
                    "success":True
                },status=HTTP_200_OK
            )
        except Exception as e:
            return Response(data={
                "message":str(e),
                "success":False
            },status = HTTP_400_BAD_REQUEST)
class MessageListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    def get_queryset(self):
        chat_id = self.kwargs['pk']
        return Message.objects.filter(chat_id=chat_id)
    def get(self,request,*args,**kwargs):
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset,many=True)
            return Response(
                data={
                    "data":serializer.data,
                    "success":True
                },status=HTTP_200_OK
            )
        except Exception as e:
            return Response(data={
                "message":str(e),
                "success":False
            },status=HTTP_400_BAD_REQUEST)
class MessageCreateView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]
    serializer_class = MessageSerializer

    def post(self,request,*args,**kwargs):
        try:
            datos = request.data
            if datos["chat"]<0:
                instnce = Chat.objects.create(user=request.user,title=datos["message_text"])
                datos['chat'] = instnce.id
            serializer = self.get_serializer(data=datos)
            if not serializer.is_valid():
                error_messages = []
                for field, errors in serializer.errors.items():
                    for error in errors:
                        error_messages.append(f"{field}: {error}")
                raise ValueError("; ".join(error_messages))
                
            serializer.save()
            return Response(
                data={
                    "data":serializer.data,
                    "success":True
                }
            )
        except Exception as e:
            return Response(
                data={
                    "message":str(e),
                    "success":False
                },status=HTTP_400_BAD_REQUEST
            )
class ChatDestroyView(DestroyAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]
    serializer_class = ChatSerializer
    queryset = Chat.objects.all()
    def destroy(self, request, *args, **kwargs):
        try:
            chat = self.get_object()
            chat.delete()
            return Response(data={
                "message":"Chat eliminado",
                "success":True
            },status=HTTP_200_OK)
        except Exception as e:
            
            return Response(data={
                "message":str(e),
                "success":False
            }) 