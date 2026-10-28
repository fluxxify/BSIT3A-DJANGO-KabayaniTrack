from django.contrib import admin

from .models import Agency, AgencyStaff


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'category', 'phone', 'is_active')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'slug', 'address', 'phone', 'website')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(AgencyStaff)
class AgencyStaffAdmin(admin.ModelAdmin):
    list_display = ('user', 'agency', 'created_at')
    list_filter = ('agency',)
    search_fields = ('user__username', 'agency__name')
