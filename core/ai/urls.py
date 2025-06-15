from django.urls import path
from .views import ChatMessageCreateView,ChatListView,MessageListView,MessageCreateView,ChatDestroyView
urlpatterns = [
    path(route="chat/create/",view=ChatMessageCreateView.as_view()),
    path(route="chat/list/",view=ChatListView.as_view()),
    path(route="chat/delete/<int:pk>/",view=ChatDestroyView.as_view()),
    path(route="chat/message/list/<int:pk>/",view=MessageListView.as_view()),
    path(route="chat/message/create/",view=MessageCreateView.as_view()),
]
