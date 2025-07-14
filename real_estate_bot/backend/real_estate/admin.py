from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import TelegramUser, Property, Favorite, UserActivity, Region, District

@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ['telegram_id', 'full_name', 'username', 'language', 'balance', 'is_blocked', 'created_at']
    list_filter = ['language', 'is_blocked', 'created_at']
    search_fields = ['telegram_id', 'username', 'first_name', 'last_name']
    list_editable = ['is_blocked', 'language']
    readonly_fields = ['telegram_id', 'created_at', 'updated_at']
    
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = "Полное имя"

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name_uz', 'name_ru', 'name_en', 'key', 'is_active']
    list_editable = ['is_active']
    search_fields = ['name_uz', 'name_ru', 'name_en', 'key']
    list_filter = ['is_active']

@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ['name_uz', 'region', 'name_ru', 'name_en', 'key', 'is_active']
    list_filter = ['region', 'is_active']
    list_editable = ['is_active']
    search_fields = ['name_uz', 'name_ru', 'name_en', 'key']

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'user', 'property_type', 'region_display', 'district_display',
        'price', 'status', 'is_premium', 'is_approved', 'views_count', 'created_at'
    ]
    list_filter = [
        'property_type', 'status', 'condition', 'is_premium', 
        'is_approved', 'is_active', 'region', 'district', 'created_at'
    ]
    search_fields = ['title', 'description', 'address', 'full_address', 'user__first_name', 'user__last_name']
    list_editable = ['is_approved', 'is_premium']
    readonly_fields = ['views_count', 'created_at', 'updated_at']
    
    def region_display(self, obj):
        return obj.region or '-'
    region_display.short_description = 'Region'
    
    def district_display(self, obj):
        return obj.district or '-'
    district_display.short_description = 'District'
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'title', 'description', 'property_type')
        }),
        ('Местоположение', {
            'fields': ('region', 'district', 'address', 'full_address')
        }),
        ('Характеристики', {
            'fields': ('price', 'area', 'rooms', 'condition', 'status')
        }),
        ('Контакты', {
            'fields': ('contact_info',)
        }),
        ('Медиа', {
            'fields': ('photo_file_ids',)
        }),
        ('Настройки', {
            'fields': ('is_premium', 'is_approved', 'is_active', 'expires_at')
        }),
        ('Статистика', {
            'fields': ('views_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_properties', 'make_premium', 'make_regular']
    
    def approve_properties(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} объявлений одобрено.')
    approve_properties.short_description = "Одобрить выбранные объявления"
    
    def make_premium(self, request, queryset):
        updated = queryset.update(is_premium=True)
        self.message_user(request, f'{updated} объявлений сделано премиум.')
    make_premium.short_description = "Сделать премиум"
    
    def make_regular(self, request, queryset):
        updated = queryset.update(is_premium=False)
        self.message_user(request, f'{updated} объявлений сделано обычными.')
    make_regular.short_description = "Сделать обычными"

@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'property', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__first_name', 'property__title']

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['user__first_name', 'user__last_name']
    readonly_fields = ['created_at']

# Customize admin site
admin.site.site_header = "Real Estate Bot Admin"
admin.site.site_title = "Real Estate Bot"
admin.site.index_title = "Панель управления"