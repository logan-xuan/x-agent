# 需求改进列表
1、开发者模式：全面下掉压缩测试tab和相关能力，新增压缩记录查询，在此tab上能看到每次压缩的记录，包含原始的sessionID对话的全部记录和压缩后请求和响应的数据。
2、开发者模式->trace. Trace Viewer改造，通过traceId，我需要看到一次请求过程中重要结点或组件执行顺序和参数响应，flowcanvas上需要反映LLM调用、tools调用、commond、skills调用、记忆存储和查询，鼠标点击其中的结点时，能查看到具体的入参和出参，请求和响应时间等关键数据。需要看清楚的执行的时序和参数以便优化和简单，清楚的掌握ReAct Loop ,Plan Mode,skills ,tools,每一次的prompt数据和响应，他们的调用关系，调用顺序，调用耗时。根据我的需求你可以先做一份详细的方案，包括日志的变更和追加。
3、fetch_content 获取网页内容数据


4、剩余的子目录发现和动态上下文是锦上添花的功能，可以根据需要择机实施！🚀
 子目录自动发现 🟢 低优先级
预计时间: 1 小时
状态: 未实施
 动态上下文注入 (!`command) 🟢 低优先级

5、加固websocket连接


预防措施建议
1. 增加 WebSocket 心跳检测
python
# 前端：定期发送 ping
setInterval(() => {
  ws.send(JSON.stringify({ type: 'ping' }));
}, 30000);  // 每30秒

# 后端：检测超时
async def check_connection_alive(websocket):
    while True:
        await asyncio.sleep(30)
        try:
            await websocket.send_json({"type": "ping"})
        except:
            break  # 连接已断开
2. 任务持久化
python
# 将任务状态保存到数据库
class TaskState:
    task_id: str
    current_step: int
    total_steps: int
    script_path: str
    status: str  # pending, running, completed, interrupted
3. 断线重连恢复
javascript
// 前端：自动重连
ws.onclose = (event) => {
  setTimeout(() => {
    reconnect(session_id, last_task_id);
  }, 3000);
};
4. 任务完成确认
python
# 后端：确保所有步骤完成后再结束
async def execute_with_confirmation(task):
    for step in task.steps:
        await execute_step(step)
        await confirm_step_completed(step.id)
    
    # 所有步骤完成后才返回最终结果
    return final_result
总结：这不是系统逻辑问题，而是 WebSocket 连接稳定性问题。建议增强连接稳定性、任务持久化和断线重连机制


# skill设计

下一步建议
Phase 2: 中期规划
引入 Embedding 向量检索
支持模糊匹配
提升匹配准确率
实现 Skill Graph 原型
定义 SkillNode 数据结构
支持技能依赖关系
Phase 3: 长期愿景
制定 SKILL.md 标准模板
定义必需的章节
提供示例模板
自动化格式检查
实现分层路由
Category Router → Skill Router → Tool Router
支持 10000+ 技能规模
✨ 核心价值实现
从"打补丁模式"升级到"架构驱动模式"
维度	硬编码方式	通用架构方式
可扩展性	线性增长	零边际成本
可维护性	代码爆炸	简洁清晰
开发效率	每次都要改代码	只需添加 SKILL.md
系统稳定性	容易引入 bug	核心逻辑稳定
团队协作	容易冲突	并行开发
现在的架构可以支持：
✅ 1000 个技能无需修改核心代码
✅ 动态加载新技能
✅ 技能热更新
✅ 分布式技能注册
✅ 技能市场（第三方技能插件）