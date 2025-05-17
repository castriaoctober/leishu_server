from django.contrib import admin
from.models import User

class UserAdmin(admin.ModelAdmin):
    list_display = ('user_name', 'email')
    list_filter = ('user_name', 'email')
    search_fields = (['user_name', 'email'])

admin.site.register(User, UserAdmin)