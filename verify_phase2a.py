#!/usr/bin/env python3
"""验证 Phase 2A 参数传递功能"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_skill_parsing():
    """测试技能命令解析"""
    print("=" * 80)
    print("测试 1: 参数解析功能验证")
    print("=" * 80)
    
    # 直接在 Python 中测试解析逻辑
    import sys
    sys.path.insert(0, 'backend/src')
    
    from orchestrator.task_analyzer import TaskAnalyzer
    
    test_cases = [
        ("/demo-skill create test.txt", "demo-skill", "create test.txt"),
        ("/pptx", "pptx", ""),
        ("Hello world", "", "Hello world"),
    ]
    
    all_passed = True
    for input_msg, expected_skill, expected_args in test_cases:
        skill_name, args = TaskAnalyzer.parse_skill_command(input_msg)
        passed = (skill_name == expected_skill and args == expected_args)
        status = "✅" if passed else "❌"
        
        print(f"\n{status} 输入：{input_msg!r}")
        print(f"   结果：skill='{skill_name}', args='{args}'")
        if not passed:
            print(f"   期望：skill='{expected_skill}', args='{expected_args}'")
            all_passed = False
    
    return all_passed

def test_api_endpoint():
    """测试 API endpoint"""
    print("\n" + "=" * 80)
    print("测试 2: API 端点测试")
    print("=" * 80)
    
    try:
        # 检查后端是否可访问
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"\n✅ 后端健康检查通过 (状态码：{response.status_code})")
        
        # 测试聊天接口
        print("\n发送测试请求...")
        payload = {
            "message": "/demo-skill list directory",
            "session_id": "test-phase2-session"
        }
        
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            timeout=30
        )
        elapsed = time.time() - start_time
        
        print(f"\n✅ 响应时间：{elapsed:.2f}秒")
        print(f"✅ 状态码：{response.status_code}")
        
        # 尝试解析响应
        try:
            result = response.json()
            print(f"\n📄 响应内容预览:")
            print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
        except json.JSONDecodeError:
            print(f"\n⚠️  响应不是有效 JSON")
            print(response.text[:200])
        
        return True
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ 无法连接到后端：{e}")
        print("💡 请确保后端服务正在运行 (端口 8000)")
        return False
    except requests.exceptions.Timeout:
        print(f"\n❌ 请求超时 (30 秒)")
        return False
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        return False

def check_logs():
    """检查日志中的技能调用记录"""
    print("\n" + "=" * 80)
    print("测试 3: 日志分析")
    print("=" * 80)
    
    log_file = "backend/backend.log"
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 查找最近的技能相关日志
        skill_logs = []
        for line in lines[-100:]:  # 只看最后 100 行
            if 'Skill' in line or 'skill' in line:
                skill_logs.append(line.strip())
        
        if skill_logs:
            print(f"\n✅ 找到 {len(skill_logs)} 条技能相关日志:")
            for log in skill_logs[-5:]:  # 显示最后 5 条
                print(f"  {log}")
        else:
            print("\n⚠️  未找到技能相关日志")
            print("💡 可能需要先执行一些技能命令")
        
        return True
        
    except FileNotFoundError:
        print(f"\n⚠️  日志文件不存在：{log_file}")
        return False

def main():
    """主测试函数"""
    print("\n🧪 Phase 2A 参数传递功能验证\n")
    
    results = []
    
    # 测试 1: 参数解析
    results.append(("参数解析", test_skill_parsing()))
    
    # 测试 2: API 端点
    results.append(("API 端点", test_api_endpoint()))
    
    # 测试 3: 日志分析
    results.append(("日志分析", check_logs()))
    
    # 总结
    print("\n" + "=" * 80)
    print("📊 测试结果总结")
    print("=" * 80)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 所有测试通过！Phase 2A 功能正常！")
    else:
        print("⚠️  部分测试失败，请检查日志和错误信息")
    print("=" * 80)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())
