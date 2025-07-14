from django.db import models
from django.utils import timezone
import json

class TelegramUser(models.Model):
    LANGUAGE_CHOICES = [
        ('uz', 'O\'zbekcha'),
        ('ru', 'Русский'),
        ('en', 'English'),
    ]
    
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default='uz')
    is_blocked = models.BooleanField(default=False)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} (@{self.username})"
    
    class Meta:
        verbose_name = "Telegram User"
        verbose_name_plural = "Telegram Users"

class Region(models.Model):
    name_uz = models.CharField(max_length=100)
    name_ru = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    key = models.CharField(max_length=50, unique=True)  # e.g., 'tashkent_city'
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name_uz
    
    class Meta:
        verbose_name = "Region"
        verbose_name_plural = "Regions"

class District(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='districts')
    name_uz = models.CharField(max_length=100)
    name_ru = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    key = models.CharField(max_length=50)  # e.g., 'chilonzor'
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.region.name_uz} - {self.name_uz}"
    
    class Meta:
        verbose_name = "District"
        verbose_name_plural = "Districts"
        unique_together = ['region', 'key']

class Property(models.Model):
    PROPERTY_TYPES = [
        ('apartment', 'Квартира'),
        ('house', 'Дом'),
        ('commercial', 'Коммерческая'),
        ('land', 'Земля'),
    ]
    
    CONDITION_CHOICES = [
        ('new', 'Новое'),
        ('good', 'Хорошее'),
        ('repair_needed', 'Требует ремонта'),
    ]
    
    STATUS_CHOICES = [
        ('sale', 'Продажа'),
        ('rent', 'Аренда'),
    ]
    
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name='properties')
    title = models.CharField(max_length=200)
    description = models.TextField()
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES)
    
    # NEW: Region and District fields
    region = models.CharField(max_length=50, blank=True, null=True)  # Region key
    district = models.CharField(max_length=50, blank=True, null=True)  # District key
    address = models.CharField(max_length=300)  # User input address
    full_address = models.CharField(max_length=500, blank=True)  # Complete address with region/district
    
    price = models.DecimalField(max_digits=12, decimal_places=2)
    area = models.IntegerField(help_text="Площадь в м²")
    rooms = models.IntegerField()
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    contact_info = models.CharField(max_length=200)
    
    # Store Telegram file_ids as JSON
    photo_file_ids = models.JSONField(default=list, blank=True)
    
    is_premium = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    views_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.title} - {self.price} сум"
    
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def get_first_photo_id(self):
        """Get first photo file_id for preview"""
        return self.photo_file_ids[0] if self.photo_file_ids else None
    
    def get_location_display(self, language='uz'):
        """Get human-readable location"""
        if self.region and self.district:
            try:
                # You can implement this with database lookup or use the REGIONS_DATA
                return self.full_address or f"{self.address}"
            except:
                return self.full_address or self.address
        return self.address
    
    class Meta:
        verbose_name = "Property"
        verbose_name_plural = "Properties"
        ordering = ['-created_at']

class Favorite(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name='favorites')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'property']
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"

class UserActivity(models.Model):
    ACTION_TYPES = [
        ('start', 'Запуск бота'),
        ('post_listing', 'Размещение объявления'),
        ('view_listing', 'Просмотр объявления'),
        ('search', 'Поиск'),
        ('favorite_add', 'Добавление в избранное'),
        ('contact', 'Обращение к продавцу'),
    ]
    
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name='activities')
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    details = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "User Activity"
        verbose_name_plural = "User Activities"