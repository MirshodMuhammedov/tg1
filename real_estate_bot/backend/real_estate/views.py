from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters_rf
from django.db.models import Q
from .models import TelegramUser, Property, Favorite, UserActivity, Region, District
from .serializers import (
    TelegramUserSerializer, PropertySerializer, PropertyListSerializer,
    FavoriteSerializer, UserActivitySerializer, RegionSerializer, DistrictSerializer
)
from . import serializers
class PropertyFilter(filters_rf.FilterSet):
    min_price = filters_rf.NumberFilter(field_name="price", lookup_expr='gte')
    max_price = filters_rf.NumberFilter(field_name="price", lookup_expr='lte')
    min_area = filters_rf.NumberFilter(field_name="area", lookup_expr='gte')
    max_area = filters_rf.NumberFilter(field_name="area", lookup_expr='lte')
    region = filters_rf.CharFilter(field_name="region", lookup_expr='exact')
    district = filters_rf.CharFilter(field_name="district", lookup_expr='exact')
    
    class Meta:
        model = Property
        fields = ['property_type', 'status', 'condition', 'region', 'district', 
                 'min_price', 'max_price', 'min_area', 'max_area']

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

@api_view(['POST'])
@permission_classes([AllowAny])
def create_or_get_user(request):
    """Create or get Telegram user"""
    telegram_id = request.data.get('telegram_id')
    if not telegram_id:
        return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    user, created = TelegramUser.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            'username': request.data.get('username', ''),
            'first_name': request.data.get('first_name', ''),
            'last_name': request.data.get('last_name', ''),
            'language': request.data.get('language', 'uz')
        }
    )
    
    if not created:
        # Update user info
        user.username = request.data.get('username', user.username)
        user.first_name = request.data.get('first_name', user.first_name)
        user.last_name = request.data.get('last_name', user.last_name)
        user.save()
    
    serializer = TelegramUserSerializer(user)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['PUT'])
@permission_classes([AllowAny])
def update_user_language(request, telegram_id):
    """Update user language"""
    try:
        user = TelegramUser.objects.get(telegram_id=telegram_id)
        user.language = request.data.get('language', user.language)
        user.save()
        serializer = TelegramUserSerializer(user)
        return Response(serializer.data)
    except TelegramUser.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class PropertyListCreateAPIView(generics.ListCreateAPIView):
    """List and create properties"""
    queryset = Property.objects.filter(is_approved=True, is_active=True).order_by('-created_at')
    serializer_class = PropertyListSerializer
    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PropertyFilter
    search_fields = ['title', 'description', 'address', 'full_address']
    ordering_fields = ['created_at', 'price', 'area']
    ordering = ['-is_premium', '-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PropertySerializer
        return PropertyListSerializer
    
    def perform_create(self, serializer):
        telegram_id = self.request.data.get('user_id')
        if telegram_id:
            try:
                user = TelegramUser.objects.get(telegram_id=telegram_id)
                serializer.save(user=user)
            except TelegramUser.DoesNotExist:
                raise serializers.ValidationError("User not found")

class PropertyDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, delete property"""
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    permission_classes = [AllowAny]
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count
        instance.views_count += 1
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def user_properties(request, telegram_id):
    """Get user's properties"""
    try:
        user = TelegramUser.objects.get(telegram_id=telegram_id)
        properties = Property.objects.filter(user=user).order_by('-created_at')
        serializer = PropertyListSerializer(properties, many=True)
        return Response(serializer.data)
    except TelegramUser.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
def add_to_favorites(request):
    """Add property to favorites"""
    telegram_id = request.data.get('user_id')
    property_id = request.data.get('property_id')
    
    if not telegram_id or not property_id:
        return Response({'error': 'user_id and property_id are required'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = TelegramUser.objects.get(telegram_id=telegram_id)
        property_obj = Property.objects.get(id=property_id)
        
        favorite, created = Favorite.objects.get_or_create(
            user=user,
            property=property_obj
        )
        
        if created:
            return Response({'message': 'Added to favorites'}, status=status.HTTP_201_CREATED)
        else:
            return Response({'message': 'Already in favorites'}, status=status.HTTP_200_OK)
    
    except TelegramUser.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Property.DoesNotExist:
        return Response({'error': 'Property not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def remove_from_favorites(request, telegram_id, property_id):
    """Remove property from favorites"""
    try:
        user = TelegramUser.objects.get(telegram_id=telegram_id)
        favorite = Favorite.objects.get(user=user, property_id=property_id)
        favorite.delete()
        return Response({'message': 'Removed from favorites'}, status=status.HTTP_200_OK)
    except TelegramUser.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Favorite.DoesNotExist:
        return Response({'error': 'Favorite not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def user_favorites(request, telegram_id):
    """Get user's favorites"""
    try:
        user = TelegramUser.objects.get(telegram_id=telegram_id)
        favorites = Favorite.objects.filter(user=user).order_by('-created_at')
        serializer = FavoriteSerializer(favorites, many=True)
        return Response(serializer.data)
    except TelegramUser.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def regions_list(request):
    """Get list of regions"""
    regions = Region.objects.filter(is_active=True)
    serializer = RegionSerializer(regions, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def districts_list(request, region_id=None):
    """Get list of districts, optionally filtered by region"""
    if region_id:
        districts = District.objects.filter(region_id=region_id, is_active=True)
    else:
        districts = District.objects.filter(is_active=True)
    
    serializer = DistrictSerializer(districts, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def districts_by_region_key(request, region_key):
    """Get districts by region key"""
    try:
        region = Region.objects.get(key=region_key, is_active=True)
        districts = District.objects.filter(region=region, is_active=True)
        serializer = DistrictSerializer(districts, many=True)
        return Response(serializer.data)
    except Region.DoesNotExist:
        return Response({'error': 'Region not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def properties_by_location(request):
    """Get properties filtered by region and/or district"""
    region_key = request.GET.get('region')
    district_key = request.GET.get('district')
    
    queryset = Property.objects.filter(is_approved=True, is_active=True)
    
    if region_key:
        queryset = queryset.filter(region=region_key)
    
    if district_key:
        queryset = queryset.filter(district=district_key)
    
    queryset = queryset.order_by('-is_premium', '-created_at')
    
    # Paginate results
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)
    
    if page is not None:
        serializer = PropertyListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    serializer = PropertyListSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def property_statistics(request):
    """Get property statistics"""
    from django.db.models import Count, Avg
    
    stats = {
        'total_properties': Property.objects.filter(is_approved=True).count(),
        'premium_properties': Property.objects.filter(is_approved=True, is_premium=True).count(),
        'properties_by_type': list(Property.objects.filter(is_approved=True)
                                  .values('property_type')
                                  .annotate(count=Count('id'))),
        'properties_by_status': list(Property.objects.filter(is_approved=True)
                                   .values('status')
                                   .annotate(count=Count('id'))),
        'properties_by_region': list(Property.objects.filter(is_approved=True)
                                   .exclude(region__isnull=True)
                                   .values('region')
                                   .annotate(count=Count('id'))),
        'average_price': Property.objects.filter(is_approved=True).aggregate(Avg('price'))['price__avg'],
        'recent_properties': PropertyListSerializer(
            Property.objects.filter(is_approved=True).order_by('-created_at')[:5],
            many=True
        ).data
    }
    
    return Response(stats)
