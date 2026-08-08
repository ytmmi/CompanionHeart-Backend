/**
 * Provider 构建 — 由启动 env 把 CompanionHeart 的 LLM 配置翻译成 pi-ai Models 集合
 *
 * env 契约（Python 侧 app/main.py:_build_agent_sidecar_env 注入）:
 *   LLM_PROVIDER  "anthropic" | "deepseek" | "custom"
 *                 anthropic/deepseek 走 pi-ai 内置 provider，其余走自定义 OpenAI 兼容端点
 *   LLM_MODEL     模型 id（如 claude-sonnet-4-6 / deepseek-v4-flash / llama3）
 *   LLM_API_KEY   API key（custom 模式必填；内置 provider 模式作为其 key 来源）
 *   LLM_BASE_URL  custom 模式必填（OpenAI 兼容端点根地址，Ollama 传 http://localhost:11434/v1）
 *                 anthropic 模式可选：仅指向代理/中转时下发
 *   LLM_TIMEOUT   秒（暂未使用，预留）
 */
import type { Model, MutableModels } from "@earendil-works/pi-ai";
import { createModels, createProvider } from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { anthropicProvider } from "@earendil-works/pi-ai/providers/anthropic";
import { deepseekProvider } from "@earendil-works/pi-ai/providers/deepseek";

export interface ProviderRuntime {
	models: MutableModels;
	model: Model<any>;
	providerId: string;
	apiKey: string;
}

const CUSTOM_PROVIDER_ID = "companionheart";

export function buildProviderRuntime(env: NodeJS.ProcessEnv = process.env): ProviderRuntime {
	const providerKind = env.LLM_PROVIDER ?? "custom";
	const modelId = env.LLM_MODEL;
	const apiKey = env.LLM_API_KEY ?? "";
	if (!modelId) throw new Error("缺少 LLM_MODEL 环境变量");

	const models = createModels();

	if (providerKind === "anthropic") {
		if (!apiKey) throw new Error("anthropic 模式缺少 LLM_API_KEY");
		models.setProvider(anthropicProvider());
		const model = models.getModel("anthropic", modelId);
		if (!model) throw new Error(`模型不在 Anthropic 内置目录: ${modelId}`);
		return { models, model, providerId: "anthropic", apiKey };
	}

	if (providerKind === "deepseek") {
		if (!apiKey) throw new Error("deepseek 模式缺少 LLM_API_KEY");
		models.setProvider(deepseekProvider());
		const model = models.getModel("deepseek", modelId);
		if (!model) throw new Error(`模型不在 DeepSeek 内置目录: ${modelId}`);
		return { models, model, providerId: "deepseek", apiKey };
	}

	// custom：任意 OpenAI 兼容端点（自建 / Ollama / vLLM 等）
	const baseUrl = env.LLM_BASE_URL;
	if (!baseUrl) throw new Error("custom 模式缺少 LLM_BASE_URL");

	const model: Model<"openai-completions"> = {
		id: modelId,
		name: modelId,
		api: "openai-completions",
		provider: CUSTOM_PROVIDER_ID,
		baseUrl,
		reasoning: false,
		input: ["text"],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: 65536,
		maxTokens: 8192,
		// 国产/自建兼容端点普遍不支持 developer role
		compat: { supportsDeveloperRole: false },
	};

	models.setProvider(
		createProvider({
			id: CUSTOM_PROVIDER_ID,
			name: "CompanionHeart LLM",
			baseUrl,
			auth: {
				apiKey: {
					name: "CompanionHeart LLM key",
					// Ollama 等无鉴权端点用占位 key，端点会忽略
					resolve: async () => ({ auth: { apiKey: apiKey || "none" }, source: "sidecar-env" }),
				},
			},
			models: [model],
			api: openAICompletionsApi(),
		}),
	);

	return { models, model, providerId: CUSTOM_PROVIDER_ID, apiKey: apiKey || "none" };
}
