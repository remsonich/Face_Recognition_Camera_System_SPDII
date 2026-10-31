#!/bin/bash

# Face Recognition API - Quick Test Script
# Tests all endpoints

BASE_URL="http://127.0.0.1:8000"
API_URL="$BASE_URL/api/v1"

echo "=========================================="
echo "Face Recognition API - Test Suite"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test 1: Health Check
echo -e "${BLUE}[1] Testing Health Check...${NC}"
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health/")
if [ "$HEALTH" = "200" ]; then
    echo -e "${GREEN}✓ Health check passed${NC}"
else
    echo -e "${RED}✗ Health check failed (Status: $HEALTH)${NC}"
fi
echo ""

# Test 2: Root Endpoint
echo -e "${BLUE}[2] Testing Root Endpoint...${NC}"
ROOT=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/")
if [ "$ROOT" = "200" ]; then
    echo -e "${GREEN}✓ Root endpoint passed${NC}"
else
    echo -e "${RED}✗ Root endpoint failed (Status: $ROOT)${NC}"
fi
echo ""

# Test 3: Create User
echo -e "${BLUE}[3] Testing User Creation...${NC}"
USER=$(curl -s -X POST "$API_URL/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_user",
    "full_name": "Test User",
    "password": "test_password",
    "role": "Employee"
  }')
echo "Response: $USER"
echo ""

# Test 4: Get Users List
echo -e "${BLUE}[4] Testing Get Users List...${NC}"
USERS=$(curl -s "$API_URL/users/")
echo "Users Count: $(echo $USERS | grep -o 'id' | wc -l)"
echo ""

# Test 5: Get User by ID
echo -e "${BLUE}[5] Testing Get User by ID...${NC}"
USER_DETAIL=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/users/1")
if [ "$USER_DETAIL" = "200" ] || [ "$USER_DETAIL" = "404" ]; then
    echo -e "${GREEN}✓ Get user endpoint working${NC}"
else
    echo -e "${RED}✗ Get user failed (Status: $USER_DETAIL)${NC}"
fi
echo ""

echo "=========================================="
echo "API Test Suite Complete!"
echo "=========================================="
echo ""
echo "📚 Full API Documentation:"
echo "   http://127.0.0.1:8000/docs"
echo ""
echo "📊 Database Management:"
echo "   Open DBeaver and connect to:"
echo "   - Host: localhost:3306"
echo "   - Database: face_recognition_db"
echo "   - Username: root"
echo "   - Password: 1362"
