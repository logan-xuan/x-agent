#!/bin/bash
# Phase 5 & 6 功能验证脚本
# 用法: ./scripts/verify_phase5_6.sh [backend_url]

set -e

BASE_URL="${1:-http://localhost:8000/api/v1}"
echo "=== Phase 5 & 6 功能验证 ==="
echo "Backend URL: $BASE_URL"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

check_response() {
    local name="$1"
    local response="$2"
    local check="$3"
    
    if echo "$response" | eval "$check" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}: $name"
        ((pass_count++))
    else
        echo -e "${RED}✗ FAIL${NC}: $name"
        echo "Response: $response"
        ((fail_count++))
    fi
}

echo "=== Phase 5: 每日记记记录 ==="

# 5.1 创建记忆条目
echo ""
echo "5.1 创建记忆条目 (POST /memory/entries)"
ENTRY_RESPONSE=$(curl -s -X POST "$BASE_URL/memory/entries" \
    -H "Content-Type: application/json" \
    -d '{
        "content": "验证测试: 用户决定使用 Vue 作为前端框架",
        "content_type": "decision"
    }')
check_response "创建决策类型条目" "$ENTRY_RESPONSE" "grep -q '\"id\"'"
ENTRY_ID=$(echo "$ENTRY_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
echo "  Entry ID: $ENTRY_ID"

# 5.2 创建对话类型条目
echo ""
echo "5.2 创建对话类型条目"
CONV_RESPONSE=$(curl -s -X POST "$BASE_URL/memory/entries" \
    -H "Content-Type: application/json" \
    -d '{
        "content": "验证测试: 讨论了系统架构，选择微服务方案",
        "content_type": "conversation"
    }')
check_response "创建对话类型条目" "$CONV_RESPONSE" "grep -q '\"id\"'"

# 5.3 列出所有记忆条目
echo ""
echo "5.3 列出记忆条目 (GET /memory/entries)"
LIST_RESPONSE=$(curl -s "$BASE_URL/memory/entries?limit=10")
check_response "列出条目" "$LIST_RESPONSE" "grep -q '\"id\"'"
TOTAL=$(echo "$LIST_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null || echo "0")
echo "  返回条目数: $TOTAL"

# 5.4 获取单个条目
if [ -n "$ENTRY_ID" ]; then
    echo ""
    echo "5.4 获取单个条目 (GET /memory/entries/{id})"
    GET_RESPONSE=$(curl -s "$BASE_URL/memory/entries/$ENTRY_ID")
    check_response "获取条目详情" "$GET_RESPONSE" "grep -q '$ENTRY_ID'"
fi

# 5.5 列出可用日期
echo ""
echo "5.5 列出可用日期 (GET /memory/dates)"
DATES_RESPONSE=$(curl -s "$BASE_URL/memory/dates")
check_response "列出日期" "$DATES_RESPONSE" "grep -q '[0-9]'"
echo "  日期列表: $(echo "$DATES_RESPONSE" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), ensure_ascii=False))" 2>/dev/null || echo "$DATES_RESPONSE")"

# 5.6 获取每日日志
TODAY=$(date +%Y-%m-%d)
echo ""
echo "5.6 获取每日日志 (GET /memory/daily/{date})"
DAILY_RESPONSE=$(curl -s "$BASE_URL/memory/daily/$TODAY")
if echo "$DAILY_RESPONSE" | grep -q '"date"'; then
    check_response "获取今日日志" "$DAILY_RESPONSE" "grep -q '$TODAY'"
else
    echo -e "${YELLOW}⚠ SKIP${NC}: 今日暂无日志 (正常情况)"
fi

# 5.7 分析内容重要性
echo ""
echo "5.7 分析内容重要性 (POST /memory/analyze)"
ANALYZE_RESPONSE=$(curl -s -X POST "$BASE_URL/memory/analyze" \
    -H "Content-Type: application/json" \
    -d '{"content": "这很重要！我们决定下周开始重构项目。"}')
check_response "分析重要性" "$ANALYZE_RESPONSE" "grep -q 'is_important'"
IS_IMPORTANT=$(echo "$ANALYZE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('is_important', False))" 2>/dev/null || echo "false")
echo "  是否重要: $IS_IMPORTANT"

# 5.8 删除条目
if [ -n "$ENTRY_ID" ]; then
    echo ""
    echo "5.8 删除条目 (DELETE /memory/entries/{id})"
    DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/memory/entries/$ENTRY_ID")
    check_response "删除条目" "$DELETE_RESPONSE" "grep -q 'deleted'"
fi

echo ""
echo "=== Phase 6: 混合搜索能力 ==="

# 6.1 搜索 - 前端框架
echo ""
echo "6.1 搜索记忆 (POST /memory/search) - 前端框架"
SEARCH1=$(curl -s -X POST "$BASE_URL/memory/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "前端框架", "limit": 5}')
check_response "搜索前端框架" "$SEARCH1" "grep -q '\"items\"'"
echo "  结果: $(echo "$SEARCH1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"共{d.get('total',0)}条\")" 2>/dev/null || echo "解析失败")"

# 6.2 搜索 - 数据库
echo ""
echo "6.2 搜索记忆 - 数据库选型"
SEARCH2=$(curl -s -X POST "$BASE_URL/memory/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "数据库选型", "limit": 5}')
check_response "搜索数据库选型" "$SEARCH2" "grep -q '\"items\"'"

# 6.3 搜索 - 带过滤条件
echo ""
echo "6.3 搜索记忆 - 带内容类型过滤"
SEARCH3=$(curl -s -X POST "$BASE_URL/memory/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "决定", "content_type": "decision", "limit": 5}')
check_response "搜索决策类型" "$SEARCH3" "grep -q '\"items\"'"

# 6.4 搜索 - 空查询
echo ""
echo "6.4 搜索记忆 - 空查询边界测试"
SEARCH_EMPTY=$(curl -s -X POST "$BASE_URL/memory/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "", "limit": 5}')
check_response "空查询返回空结果" "$SEARCH_EMPTY" "grep -q '\"items\":\\[\\]'"

# 6.5 相似搜索
echo ""
echo "6.5 相似搜索 (GET /memory/search/similar/{id})"
# 先获取一个条目ID
FIRST_ENTRY=$(curl -s "$BASE_URL/memory/entries?limit=1")
FIRST_ID=$(echo "$FIRST_ENTRY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'] if isinstance(d,list) and len(d)>0 else '')" 2>/dev/null || echo "")
if [ -n "$FIRST_ID" ]; then
    SIMILAR_RESPONSE=$(curl -s "$BASE_URL/memory/search/similar/$FIRST_ID?limit=5")
    check_response "查找相似条目" "$SIMILAR_RESPONSE" "grep -q '\"items\"'"
else
    echo -e "${YELLOW}⚠ SKIP${NC}: 无条目可用于相似搜索"
fi

# 6.6 分页测试
echo ""
echo "6.6 搜索分页测试"
PAGE1=$(curl -s -X POST "$BASE_URL/memory/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "测试", "limit": 2, "offset": 0}')
PAGE2=$(curl -s -X POST "$BASE_URL/memory/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "测试", "limit": 2, "offset": 2}')
check_response "分页查询第一页" "$PAGE1" "grep -q '\"items\"'"
check_response "分页查询第二页" "$PAGE2" "grep -q '\"items\"'"

echo ""
echo "=== 验证结果汇总 ==="
echo -e "${GREEN}通过: $pass_count${NC}"
echo -e "${RED}失败: $fail_count${NC}"

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}所有功能验证通过！${NC}"
    exit 0
else
    echo -e "${RED}存在失败的测试项，请检查！${NC}"
    exit 1
fi
