#!/bin/bash

echo "======================================"
echo "Web Search 集成验证脚本"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查计数
PASSED=0
FAILED=0

# 1. 检查后端文件
echo "1️⃣  检查后端 API 端点..."
if grep -q "web_search_debug" backend/src/api/v1/dev.py; then
    echo -e "${GREEN}✓${NC} 后端 API 端点已添加"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} 后端 API 端点未找到"
    ((FAILED++))
fi

# 2. 检查前端组件
echo ""
echo "2️⃣  检查前端组件..."
if [ -f "frontend/src/components/dev/WebSearchDebugger.tsx" ]; then
    echo -e "${GREEN}✓${NC} WebSearchDebugger 组件存在"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} WebSearchDebugger 组件不存在"
    ((FAILED++))
fi

# 3. 检查组件导出
echo ""
echo "3️⃣  检查组件导出..."
if grep -q "WebSearchDebugger" frontend/src/components/dev/index.ts; then
    echo -e "${GREEN}✓${NC} 组件已导出"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} 组件未导出"
    ((FAILED++))
fi

# 4. 检查 DevModeWindow 集成
echo ""
echo "4️⃣  检查开发者模式集成..."
if grep -q "web_search" frontend/src/components/dev/DevModeWindow.tsx; then
    echo -e "${GREEN}✓${NC} 已集成到开发者模式"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} 未集成到开发者模式"
    ((FAILED++))
fi

# 5. 检查单元测试
echo ""
echo "5️⃣  检查单元测试..."
if [ -f "backend/tests/unit/test_web_search.py" ]; then
    echo -e "${GREEN}✓${NC} 单元测试文件存在"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} 单元测试文件不存在"
    ((FAILED++))
fi

# 6. 运行单元测试（可选）
echo ""
echo "6️⃣  运行单元测试（前 4 个初始化测试）..."
cd backend
if uv run pytest tests/unit/test_web_search.py::TestWebSearchToolInitialization -v --tb=short 2>&1 | grep -q "4 passed"; then
    echo -e "${GREEN}✓${NC} 单元测试通过"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠${NC} 单元测试执行失败或跳过"
    ((FAILED++))
fi
cd ..

# 7. 检查导入语句
echo ""
echo "7️⃣  检查后端导入..."
if grep -q "from ...tools.builtin import WebSearchTool" backend/src/api/v1/dev.py; then
    echo -e "${GREEN}✓${NC} WebSearchTool 已导入"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} WebSearchTool 未导入"
    ((FAILED++))
fi

# 总结
echo ""
echo "======================================"
echo "验证结果汇总"
echo "======================================"
echo -e "通过：${GREEN}${PASSED}${NC}"
echo -e "失败：${RED}${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ 所有检查通过！Web Search 已成功集成到开发者模式${NC}"
    echo ""
    echo "📝 使用方式:"
    echo "   1. 启动后端服务：cd backend && uv run python -m uvicorn src.main:app --reload"
    echo "   2. 启动前端服务：cd frontend && yarn dev"
    echo "   3. 打开浏览器访问 http://localhost:5173"
    echo "   4. 点击右上角「开发者模式」按钮"
    echo "   5. 切换到「Web Search」标签页"
    echo "   6. 输入搜索关键词进行测试"
    exit 0
else
    echo -e "${RED}❌ 部分检查失败，请查看上方输出${NC}"
    exit 1
fi
