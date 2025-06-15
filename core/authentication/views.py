from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.status import HTTP_200_OK,HTTP_401_UNAUTHORIZED,HTTP_400_BAD_REQUEST
from django.contrib.auth import authenticate
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
# Create your views here.
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def post(self, request, *args, **kwargs):
        try:
            username = request.data.get("username")
            password = request.data.get("password")
            user = authenticate(username=username,password=password)
            if user is not None:
                refresh = RefreshToken.for_user(user)
                response = Response(data={
                    "success":True,
                    "message":"Login exitoso"
                },status=HTTP_200_OK)
                response.set_cookie(
                    key="access_token",
                    value=str(refresh.access_token),
                    httponly=True,
                    samesite="Lax",
                    path="/",
                    secure=False
                )
                return response
            else:
                return Response(data={
                    "success":False,
                    "message":"Credenciales invalidas"
                },status=HTTP_401_UNAUTHORIZED)

        except Exception as e:
        
            return Response(data={
                'error': str(e),
                'success': False
            },status=HTTP_400_BAD_REQUEST)
        
class LogoutView(APIView):
    def post(self,request,*args,**kwargs):
        response = Response({'success':True,'message':"Sesión cerrada"},status=HTTP_200_OK)
        response.delete_cookie('access_token')
        return response
class VerifyToken(APIView):
    permission_classes = [IsAuthenticated]
    def get(self,request,*args,**kwargs):
        try:
            return Response(data={
                "success":True,
                "message":"Valido"
            },status=HTTP_200_OK)
        except Exception as e:
            return Response(
                data={
                    "message":str(e),
                    "success":False
                },status=HTTP_400_BAD_REQUEST
            )