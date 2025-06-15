from django.db import models
from django.contrib.auth.models import User
from django.forms import model_to_dict
# Create your models here.
class Chat(models.Model):
    user = models.ForeignKey(User,on_delete=models.DO_NOTHING,verbose_name="Usuario")
    title = models.CharField(max_length=200,verbose_name="Titulo")
    created_at = models.DateTimeField(auto_now_add=True)
    update_at = models.DateField(auto_now=True)
    class Meta:
        verbose_name = "Chat"
        verbose_name_plural ="Chats"
        db_table = "chats"
class Message(models.Model):
    SENDER_CHOICES = [
        ('user',"User"),
        ("ai","AI")
    ]
    chat = models.ForeignKey(Chat,on_delete=models.CASCADE,verbose_name="Chat")
    sender = models.CharField(max_length=4,choices=SENDER_CHOICES)
    message_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = "Mensaje"
        verbose_name_plural = "Mensajes"
        db_table = "messages"
    def toJSON(self):
        item = model_to_dict(self)
        item['chat_id'] = self.chat.id
        return item