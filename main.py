from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.api import logger
import datetime


@register(
    "astrbot_plugin_group_monitor",
    "DITF16",
    "监控指定群的成员退群事件，并发送详细通知到管理群",
    "v1.0.0",
    "https://github.com/DITF16/astrbot_plugin_group_monitor",
)
class GroupMonitorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # 初始化监控映射
        # 将配置中的 list ["monitor:notify"] 转换为 dict {monitor: notify}
        self.monitored_map = {}
        raw_list = self.config.get("monitored_groups", [])
        for item in raw_list:
            if isinstance(item, str) and ":" in item:
                m_gid, n_gid = item.split(":", 1)
                self.monitored_map[m_gid] = n_gid

    def _save_monitored_map(self):
        """将内存中的字典转换回列表格式并保存到配置文件"""
        save_list = [f"{k}:{v}" for k, v in self.monitored_map.items()]
        self.config["monitored_groups"] = save_list
        self.config.save_config()

    def _is_admin(self, event: AiocqhttpMessageEvent) -> bool:
        """检查发送者是否在管理员列表中"""
        sender_id = str(event.get_sender_id())
        # 获取配置中的管理员列表，并将所有 ID 转为字符串进行比对
        admin_list = [str(uid) for uid in self.config.get("admins", [])]

        # 也可以保留超级管理员权限(可选): if event.is_admin(): return True
        return sender_id in admin_list

    async def _safe_get_group_name(self, event, group_id):
        """安全获取群名称，失败返回未知"""
        try:
            group_info = await event.get_group(group_id)
            return f"{group_info.group_name}({group_id})"
        except Exception:
            return f"未知群聊({group_id})"

    @filter.command("群变动菜单")
    async def show_menu(self, event: AiocqhttpMessageEvent):
        """显示群变动监控插件的帮助菜单"""
        menu = (
            "【群变动监控菜单】\n"
            "1. 通知群列表\n"
            "2. 添加通知群 <群号>\n"
            "3. 删除通知群 <群号>\n"
            "4. 监控群列表\n"
            "5. 添加监控群 <监控群号> <通知群号>\n"
            "6. 删除监控群 <监控群号>\n"
            "------------------\n"
            "功能：当监控群有人退群时，自动通知对应的通知群。"
        )
        yield event.plain_result(menu)

    @filter.command("通知群列表")
    async def list_notification_groups(self, event: AiocqhttpMessageEvent):
        """查看所有接收通知的群"""
        if not self._is_admin(event):
            yield event.plain_result("🚫 暂无权限，请联系管理员添加您的QQ号到配置列表。")
            return

        notif_groups = self.config.get("notification_groups", [])
        if not notif_groups:
            yield event.plain_result("当前没有设置任何通知群。")
            return

        msg_lines = ["【通知群列表】"]
        for gid in notif_groups:
            name_str = await self._safe_get_group_name(event, gid)
            msg_lines.append(f"- {name_str}")

        yield event.plain_result("\n".join(msg_lines))

    @filter.command("添加通知群")
    async def add_notification_group(self, event: AiocqhttpMessageEvent, group_id: str):
        """添加一个群到通知列表"""
        if not self._is_admin(event):
            yield event.plain_result("🚫 暂无权限")
            return

        if not group_id:
            yield event.plain_result("请提供群号，例如：/添加通知群 123456789")
            return

        notif_groups = self.config.get("notification_groups", [])
        if group_id in notif_groups:
            yield event.plain_result(f"群 {group_id} 已在通知列表中。")
        else:
            notif_groups.append(str(group_id))
            self.config["notification_groups"] = notif_groups
            self.config.save_config()

            name_str = await self._safe_get_group_name(event, group_id)
            yield event.plain_result(f"已添加群 {name_str} 到通知列表。")

    @filter.command("删除通知群")
    async def del_notification_group(self, event: AiocqhttpMessageEvent, group_id: str):
        """从通知列表中删除一个群"""
        if not self._is_admin(event):
            yield event.plain_result("🚫 暂无权限")
            return

        notif_groups = self.config.get("notification_groups", [])
        if group_id in notif_groups:
            notif_groups.remove(str(group_id))
            self.config["notification_groups"] = notif_groups
            self.config.save_config()
            yield event.plain_result(f"已将群 {group_id} 移除出通知列表。")
        else:
            yield event.plain_result(f"群 {group_id} 不在通知列表中。")

    @filter.command("监控群列表")
    async def list_monitored_groups(self, event: AiocqhttpMessageEvent):
        """查看所有被监控的群，按通知群分组"""
        if not self._is_admin(event):
            yield event.plain_result("🚫 暂无权限")
            return

        if not self.monitored_map:
            yield event.plain_result("当前没有设置任何监控群。")
            return

        # 按通知群分组
        grouped = {}
        for mon_gid, not_gid in self.monitored_map.items():
            if not_gid not in grouped:
                grouped[not_gid] = []
            grouped[not_gid].append(mon_gid)

        msg_lines = ["【监控群列表】"]

        for not_gid, mon_list in grouped.items():
            # 获取通知群名称
            not_name_str = await self._safe_get_group_name(event, not_gid)
            msg_lines.append(f"\n通知群: {not_name_str}")

            for m_gid in mon_list:
                # 获取监控群名称
                m_name_str = await self._safe_get_group_name(event, m_gid)
                msg_lines.append(f"  └─ 监控: {m_name_str}")

        msg_lines.append("\n【汇总】")
        msg_lines.append("所有监控群号: " + ", ".join(self.monitored_map.keys()))

        yield event.plain_result("\n".join(msg_lines))

    @filter.command("添加监控群")
    async def add_monitored_group(self, event: AiocqhttpMessageEvent, monitor_gid: str, notify_gid: str = None):
        """添加监控群，必须指定通知群"""
        if not self._is_admin(event):
            yield event.plain_result("🚫 暂无权限")
            return

        if not monitor_gid:
            yield event.plain_result("请指定监控群号。")
            return

        if not notify_gid:
            yield event.plain_result("提示：未设置通知群群号。请使用格式：/添加监控群 <监控群号> <通知群号>")
            return

        monitor_gid = str(monitor_gid)
        notify_gid = str(notify_gid)

        # 更新字典并保存
        self.monitored_map[monitor_gid] = notify_gid
        self._save_monitored_map()

        # 获取名称以便反馈
        m_name_str = await self._safe_get_group_name(event, monitor_gid)
        n_name_str = await self._safe_get_group_name(event, notify_gid)

        msg = f"已添加对群 {m_name_str} 的监控，通知将发送至 {n_name_str}。"

        # 检查通知群是否在列表中，不在则添加
        notif_groups = self.config.get("notification_groups", [])
        if notify_gid not in notif_groups:
            notif_groups.append(notify_gid)
            self.config["notification_groups"] = notif_groups
            self.config.save_config()
            msg += f"\n(检测到通知群不在列表中，已自动添加)"

        yield event.plain_result(msg)

    @filter.command("删除监控群")
    async def del_monitored_group(self, event: AiocqhttpMessageEvent, monitor_gid: str):
        """删除对某群的监控"""
        if not self._is_admin(event):
            yield event.plain_result("🚫 暂无权限")
            return

        monitor_gid = str(monitor_gid)

        if monitor_gid in self.monitored_map:
            del self.monitored_map[monitor_gid]
            self._save_monitored_map()
            yield event.plain_result(f"已停止监控群 {monitor_gid}。")
        else:
            yield event.plain_result(f"群 {monitor_gid} 当前未被监控。")

    # 监听所有消息事件，从中筛选出群成员减少的 Notice 事件
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_decrease(self, event: AiocqhttpMessageEvent):
        # 鉴权：事件处理不需要检查管理员权限，因为这是自动触发的功能

        if event.get_platform_name() != "aiocqhttp":
            return

        raw_data = event.message_obj.raw_message
        if not isinstance(raw_data, dict):
            return

        # 检查是否为 notice 类型且为 group_decrease
        post_type = raw_data.get("post_type")
        notice_type = raw_data.get("notice_type")

        if post_type != "notice" or notice_type != "group_decrease":
            return

        group_id = str(raw_data.get("group_id", ""))
        user_id = str(raw_data.get("user_id", ""))
        operator_id = str(raw_data.get("operator_id", ""))
        sub_type = raw_data.get("sub_type", "")

        # 检查该群是否在监控列表中
        if group_id not in self.monitored_map:
            return

        target_notify_gid = self.monitored_map[group_id]
        client = event.bot
        nickname = "未知用户"

        # 1. 获取退群群聊名称
        group_name_str = await self._safe_get_group_name(event, group_id)

        # 2. 尝试获取退群者信息
        try:
            info = await client.get_stranger_info(user_id=int(user_id))
            nickname = info.get("nickname", "未知昵称")
        except Exception as e:
            logger.warning(f"获取退群者信息失败: {e}")

        # 构建通知消息
        leave_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reason = "主动退群"
        if sub_type == "kick":
            reason = f"被管理员({operator_id})踢出"
        elif sub_type == "kick_me":
            reason = "登录号被踢"

        msg = (
            f"【群成员变动通知】\n"
            f"时间: {leave_time}\n"
            f"退群群聊: {group_name_str}\n"
            f"用户QQ: {user_id}\n"
            f"用户昵称: {nickname}\n"
            f"变动类型: {reason}"
        )

        # 发送通知
        try:
            await client.send_group_msg(group_id=int(target_notify_gid), message=msg)
            logger.info(f"已发送退群通知到 {target_notify_gid}")
        except Exception as e:
            logger.error(f"发送退群通知失败: {e}")