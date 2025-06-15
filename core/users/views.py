from django.shortcuts import render
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK,HTTP_400_BAD_REQUEST
from rest_framework.permissions import IsAuthenticated
from core.middleware import CookieJWTAuthentication
from django.contrib.auth.models import User
from .serializer import UserSerializer
# Create your views here.

class UserListView(ListAPIView):
    def get(self, request, *args, **kwargs):
        return 
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user  # Ya está autenticado, no necesitas buscarlo por ID
            serializer = UserSerializer(user)
            return Response(data={
                "data": serializer.data,
                "success": True
            }, status=HTTP_200_OK)
        except Exception as e:
            return Response(data={
                "message": str(e),
                "success": False
            }, status=HTTP_400_BAD_REQUEST)