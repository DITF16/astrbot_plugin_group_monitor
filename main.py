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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("通知群列表")
    async def list_notification_groups(self, event: AiocqhttpMessageEvent):
        """查看所有接收通知的群"""
        notif_groups = self.config.get("notification_groups", [])
        if not notif_groups:
            yield event.plain_result("当前没有设置任何通知群。")
            return

        msg = "【通知群列表】\n" + "\n".join([f"- {gid}" for gid in notif_groups])
        yield event.plain_result(msg)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("添加通知群")
    async def add_notification_group(self, event: AiocqhttpMessageEvent, group_id: str):
        """添加一个群到通知列表"""
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
            yield event.plain_result(f"已添加群 {group_id} 到通知列表。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除通知群")
    async def del_notification_group(self, event: AiocqhttpMessageEvent, group_id: str):
        """从通知列表中删除一个群"""
        notif_groups = self.config.get("notification_groups", [])
        if group_id in notif_groups:
            notif_groups.remove(str(group_id))
            self.config["notification_groups"] = notif_groups
            self.config.save_config()
            yield event.plain_result(f"已将群 {group_id} 移除出通知列表。")
        else:
            yield event.plain_result(f"群 {group_id} 不在通知列表中。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("监控群列表")
    async def list_monitored_groups(self, event: AiocqhttpMessageEvent):
        """查看所有被监控的群，按通知群分组"""
        monitored_map = self.config.get("monitored_groups", {})  # {monitor_gid: notify_gid}
        if not monitored_map:
            yield event.plain_result("当前没有设置任何监控群。")
            return

        # 按通知群分组
        grouped = {}  # {notify_gid: [monitor_gid, ...]}
        for mon_gid, not_gid in monitored_map.items():
            if not_gid not in grouped:
                grouped[not_gid] = []
            grouped[not_gid].append(mon_gid)

        msg_lines = ["【监控群列表】"]

        # 显示分组信息
        for not_gid, mon_list in grouped.items():
            msg_lines.append(f"\n通知群: {not_gid}")
            for m_gid in mon_list:
                msg_lines.append(f"  └─ 监控: {m_gid}")

        # 显示所有监控群群号
        msg_lines.append("\n【汇总】")
        msg_lines.append("所有监控群号: " + ", ".join(monitored_map.keys()))

        yield event.plain_result("\n".join(msg_lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("添加监控群")
    async def add_monitored_group(self, event: AiocqhttpMessageEvent, monitor_gid: str, notify_gid: str = None):
        """添加监控群，必须指定通知群"""
        if not monitor_gid:
            yield event.plain_result("请指定监控群号。")
            return

        if not notify_gid:
            yield event.plain_result("提示：未设置通知群群号。请使用格式：/添加监控群 <监控群号> <通知群号>")
            return

        monitor_gid = str(monitor_gid)
        notify_gid = str(notify_gid)

        # 更新监控映射
        monitored_map = self.config.get("monitored_groups", {})
        monitored_map[monitor_gid] = notify_gid
        self.config["monitored_groups"] = monitored_map

        msg = f"已添加对群 {monitor_gid} 的监控，通知将发送至 {notify_gid}。"

        # 检查通知群是否在列表中，不在则添加
        notif_groups = self.config.get("notification_groups", [])
        if notify_gid not in notif_groups:
            notif_groups.append(notify_gid)
            self.config["notification_groups"] = notif_groups
            msg += f"\n(检测到 {notify_gid} 不在通知列表中，已自动添加)"

        self.config.save_config()
        yield event.plain_result(msg)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除监控群")
    async def del_monitored_group(self, event: AiocqhttpMessageEvent, monitor_gid: str):
        """删除对某群的监控"""
        monitored_map = self.config.get("monitored_groups", {})
        monitor_gid = str(monitor_gid)

        if monitor_gid in monitored_map:
            del monitored_map[monitor_gid]
            self.config["monitored_groups"] = monitored_map
            self.config.save_config()
            yield event.plain_result(f"已停止监控群 {monitor_gid}。")
        else:
            yield event.plain_result(f"群 {monitor_gid} 当前未被监控。")

    # 监听所有消息事件，从中筛选出群成员减少的 Notice 事件
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_decrease(self, event: AiocqhttpMessageEvent):
        # 确保是 aiocqhttp 平台
        if event.get_platform_name() != "aiocqhttp":
            return

        # AstrBot 将原始事件数据存储在 message_obj.raw_message 中
        # 对于 aiocqhttp，这是一个包含 OneBot 标准事件字段的字典
        raw_data = event.message_obj.raw_message
        if not isinstance(raw_data, dict):
            return

        # 检查是否为 notice 类型且为 group_decrease
        post_type = raw_data.get("post_type")
        notice_type = raw_data.get("notice_type")

        if post_type != "notice" or notice_type != "group_decrease":
            return

        # 获取相关ID
        group_id = str(raw_data.get("group_id", ""))
        user_id = str(raw_data.get("user_id", ""))
        operator_id = str(raw_data.get("operator_id", ""))
        sub_type = raw_data.get("sub_type", "")  # leave, kick, kick_me

        # 检查该群是否在监控列表中
        monitored_map = self.config.get("monitored_groups", {})
        if group_id not in monitored_map:
            return

        target_notify_gid = monitored_map[group_id]

        # 此时定义 client，确保在下方 try 和 send_group_msg 中均可用
        client = event.bot
        nickname = "未知用户"

        # 尝试获取退群者信息（需要异步调用）
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
            f"退群群号: {group_id}\n"
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