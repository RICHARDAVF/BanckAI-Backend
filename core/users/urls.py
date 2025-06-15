from django.urls import path
from .views import UserListView,UserProfileView
urlpatterns =[
    path(route='list/',view=UserProfileView.as_view())
]