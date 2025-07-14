from rest_framework import serializers
from .models import TelegramUser, Property, Favorite, UserActivity, Region, District

class TelegramUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramUser
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = '__all__'

class DistrictSerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name_uz', read_only=True)
    
    class Meta:
        model = District
        fields = '__all__'

class PropertySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.first_name', read_only=True)
    region_name = serializers.SerializerMethodField()
    district_name = serializers.SerializerMethodField()
    
    def get_region_name(self, obj):
        if obj.region:
            try:
                region = Region.objects.get(key=obj.region)
                return region.name_uz
            except Region.DoesNotExist:
                return obj.region
        return None
    
    def get_district_name(self, obj):
        if obj.region and obj.district:
            try:
                region = Region.objects.get(key=obj.region)
                district = District.objects.get(region=region, key=obj.district)
                return district.name_uz
            except (Region.DoesNotExist, District.DoesNotExist):
                return obj.district
        return None
    
    class Meta:
        model = Property
        fields = '__all__'
        read_only_fields = ['user', 'views_count', 'created_at', 'updated_at']

class PropertyListSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.first_name', read_only=True)
    first_photo_id = serializers.CharField(source='get_first_photo_id', read_only=True)
    location_display = serializers.SerializerMethodField()
    
    def get_location_display(self, obj):
        return obj.get_location_display()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'price', 'area', 'rooms', 'property_type', 
            'status', 'address', 'full_address', 'location_display',
            'region', 'district', 'is_premium', 'user_name', 
            'first_photo_id', 'created_at'
        ]

class FavoriteSerializer(serializers.ModelSerializer):
    property = PropertyListSerializer(read_only=True)
    
    class Meta:
        model = Favorite
        fields = ['id', 'property', 'created_at']

class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = '__all__'
        read_only_fields = ['created_at']