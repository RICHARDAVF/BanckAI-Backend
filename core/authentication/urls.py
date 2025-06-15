from django.urls import path
# from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView,TokenVerifyView
from .views import LoginView,VerifyToken
urlpatterns= [
    path('login/',LoginView.as_view()),
    # path('token/refresh/',TokenRefreshView.as_view()),
    path('token/verify/',VerifyToken.as_view())
]