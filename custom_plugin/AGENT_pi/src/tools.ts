/**
 * 桌宠工具集 — 白名单硬编码（安全边界：只在此文件注册的工具可被 agent 调用）
 *
 * Phase 2b: get_time（打通 工具调用 → tool_execution 事件 → SSE tool 事件 全链路）
 * 后续桌宠工具（天气/日程/Live2D）按同样模式添加：
 *   实现回调后端 HTTP —— 能力实现留在 Python，pi 只负责决策。
 */
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "@earendil-works/pi-ai";
import type { ToolRuntimeContext } from "./types.ts";

/** 当前时间工具（本地实现，无需回调后端） */
const getTimeTool: AgentTool = {
	name: "get_time",
	label: "获取当前时间",
	description:
		"获取当前的日期与时间。当用户询问现在几点、今天日期、星期几等时间相关问题时使用。",
	parameters: Type.Object({}),
	execute: async (_toolCallId, _params, _signal) => {
		const now = new Date();
		const weekdays = ["日", "一", "二", "三", "四", "五", "六"];
		const text =
			`${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ` +
			`星期${weekdays[now.getDay()]} ` +
			`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
		return { content: [{ type: "text", text }], details: { time: text } };
	},
};

function createDelegateWorkTool(context: ToolRuntimeContext): AgentTool {
	return {
		name: "delegate_work",
		label: "委派工作任务",
		description:
			"把需要执行、检索、生成文件或多步骤处理的工作任务交给独立工作 Agent。立即返回 job_id，不要声称任务已经完成。普通陪伴聊天不要使用。",
		parameters: Type.Object({
			task: Type.String({ description: "清晰、完整且不含生活记忆画像的工作任务" }),
			acceptance_criteria: Type.Optional(Type.Array(Type.String())),
			constraints: Type.Optional(Type.Array(Type.String())),
		}),
		execute: async (_toolCallId, params: any, signal) => {
			const endpoint = process.env.WORK_DELEGATE_URL ?? "http://127.0.0.1:18000/api/work/jobs";
			const response = await fetch(endpoint, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-Companion-User-Id": context.stable_user_id,
				},
				body: JSON.stringify({
					role_name_en: context.role_name_en,
					task: params.task,
					acceptance_criteria: params.acceptance_criteria ?? [],
					constraints: params.constraints ?? [],
					// 工具权限只能由后端策略授予，模型不能在此请求扩大权限。
					allowed_capabilities: [],
				}),
				signal,
			});
			if (!response.ok) {
				throw new Error(`工作任务委派失败(${response.status})`);
			}
			const job = (await response.json()) as {
				job_id: string;
				status: string;
				user_facing_summary?: string;
			};
			const text = `工作任务已委派，job_id=${job.job_id}，当前状态=${job.status}。请告知用户任务已开始处理，不要虚构完成结果。`;
			return { content: [{ type: "text", text }], details: job };
		},
	};
}

function createDeveloperMemoryQueryTool(context: ToolRuntimeContext): AgentTool {
	return {
		name: "developer_memory_query",
		label: "开发者全记忆查询",
		description:
			"仅在已认证开发模式中，通过后端受控网关查询生活、工作或开发记忆。七天工作原始存档必须将 include_work_archive 显式设为 true。不得尝试直接读取记忆文件。",
		parameters: Type.Object({
			text: Type.String({ description: "查询文本" }),
			domains: Type.Optional(Type.Array(Type.String())),
			role_name_en: Type.Optional(Type.String()),
			include_work_archive: Type.Optional(Type.Boolean()),
			top_k: Type.Optional(Type.Number({ minimum: 1, maximum: 20 })),
		}),
		execute: async (_toolCallId, params: any, signal) => {
			if (!context.developer_session_id || !context.client_id) {
				throw new Error("缺少已认证开发会话上下文");
			}
			const endpoint = process.env.DEVELOPER_MEMORY_QUERY_URL ?? "http://127.0.0.1:18000/api/developer/memory/query";
			const response = await fetch(endpoint, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-Developer-Session-Id": context.developer_session_id,
					"X-Companion-Client-Id": context.client_id,
					"X-Companion-User-Id": context.stable_user_id,
				},
				body: JSON.stringify({
					text: params.text,
					domains: params.domains,
					role_name_en: params.role_name_en,
					include_work_archive: params.include_work_archive ?? false,
					top_k: Math.min(params.top_k ?? 10, 20),
				}),
				signal,
			});
			if (!response.ok) throw new Error(`开发者记忆查询失败(${response.status})`);
			const result = (await response.json()) as { audit_id: string; hits: Array<any> };
			const lines = result.hits.slice(0, 20).map((hit) =>
				`[${hit.domain}/${hit.role_name_en}] ${String(hit.content).slice(0, 1200)}`,
			);
			const text = `audit_id=${result.audit_id}\n${lines.join("\n") || "没有匹配记忆"}`;
			return {
				content: [{ type: "text", text }],
				details: { audit_id: result.audit_id, hit_count: result.hits.length },
			};
		},
	};
}

/** 白名单：陪伴工具固定，工作域只有 delegate_work 这一道入口。 */
export function createPetTools(context?: ToolRuntimeContext): AgentTool[] {
	const tools: AgentTool[] = [getTimeTool];
	if (context?.developer_session_id) tools.push(createDeveloperMemoryQueryTool(context));
	else if (context) tools.push(createDelegateWorkTool(context));
	return tools;
}

export const TOOL_NAMES: string[] = ["get_time", "delegate_work", "developer_memory_query"];
