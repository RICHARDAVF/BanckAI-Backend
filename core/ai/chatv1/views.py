from rest_framework.response import Response
from rest_framework.generics import GenericAPIView
from core.middleware import CookieJWTAuthentication
from rest_framework.status import HTTP_200_OK,HTTP_400_BAD_REQUESTT
from ..models import Message,Chat
class ChatMessageView(GenericAPIView):
    def post(self,request,*args,**kwargs):
        try:
            user = request.user
            text = request.data['message_text']
            chat_id = request.data['chat']
            history_chat = list(
                Message.objects.filter(
                    chat_id=chat_id
                ).order_by('-created_at')[:10]
                .values('message_text','sender')
            )
            
        except Exception as e:
            return Response(data={
                "message":str(e),
                "success":False
            },status=HTTP_400_BAD_REQUESTT)