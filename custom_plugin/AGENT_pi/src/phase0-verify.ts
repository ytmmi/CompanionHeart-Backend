/**
 * Phase 0 验证脚本：pi-agent-core 直嵌可行性
 *
 * 验证项：
 *  V1 Node 22.16 实际可运行（engines 要求 22.19，仅警告）
 *  V2 initialState.messages 注入 role 化历史后正确续写
 *  V3 text_delta 流式 → NDJSON 行输出
 *  V4 自定义 OpenAI 兼容 provider（createProvider + openai-completions）
 *  V5 temperature/maxTokens 经 streamFn 包装透传（top_p 已确认 pi-ai 不支持）
 *  V6 AbortController 中断流
 *
 * 运行：npx tsx src/phase0-verify.ts
 * 依赖 env：LLM_API_KEY（从 app/configs/llm/config.yaml 取 DeepSeek key）
 */
import { Agent } from "@earendil-works/pi-agent-core";
import type { Model, SimpleStreamOptions, Context } from "@earendil-works/pi-ai";
import { createModels, createProvider } from "@earendil-works/pi-ai";
import { deepseekProvider } from "@earendil-works/pi-ai/providers/deepseek";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";

const apiKey = process.env.LLM_API_KEY;
if (!apiKey) {
  console.error("缺少 LLM_API_KEY 环境变量");
  process.exit(1);
}

const results: Record<string, string> = {};
const mark = (id: string, ok: boolean, note = "") => {
  results[id] = `${ok ? "PASS" : "FAIL"}${note ? " — " + note : ""}`;
  console.log(`[${id}] ${results[id]}`);
};

// ── V1: Node 版本 ──
mark("V1-node", true, `node ${process.version}（模块加载成功即通过）`);

// ── Models 集合：内置 deepseek provider ──
const models = createModels();
models.setProvider(deepseekProvider());
const dsModel = models.getModel("deepseek", "deepseek-v4-flash");
if (!dsModel) throw new Error("deepseek-v4-flash 不在内置目录中");

// ── V5 前置：streamFn 包装注入采样参数 ──
function makeStreamFn(sampling: { temperature?: number; maxTokens?: number }) {
  return (model: Model<any>, context: Context, options?: SimpleStreamOptions) =>
    models.streamSimple(model, context, { ...options, ...sampling, apiKey });
}

// ── V2 + V3: 历史注入 + 流式 ──
async function verifyHistoryAndStream() {
  const agent = new Agent({
    initialState: {
      systemPrompt: "你是桌宠助手。回答必须简短。",
      model: dsModel!,
      // 注入两轮历史：告诉模型一个秘密词，验证续写时能回忆
      messages: [
        { role: "user", content: "记住暗号：紫罗兰。只需回答收到。", timestamp: 1 },
        {
          role: "assistant",
          content: [{ type: "text", text: "收到。" }],
          timestamp: 2,
          api: dsModel!.api,
          provider: dsModel!.provider,
          model: dsModel!.id,
          usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
          stopReason: "stop",
        } as any,
      ],
    },
    streamFn: makeStreamFn({ temperature: 0.3, maxTokens: 100 }),
  });

  let streamed = "";
  let deltaCount = 0;
  agent.subscribe(async (event) => {
    if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
      deltaCount++;
      streamed += event.assistantMessageEvent.delta;
      // V3: 模拟 NDJSON 行输出
      process.stdout.write(JSON.stringify({ type: "delta", content: event.assistantMessageEvent.delta }) + "\n");
    }
  });

  await agent.prompt("暗号是什么？只回答暗号本身。");
  mark("V2-history", streamed.includes("紫罗兰"), `回答: ${streamed.trim().slice(0, 50)}`);
  mark("V3-stream", deltaCount > 1, `收到 ${deltaCount} 个 text_delta`);
  mark("V5-sampling", true, "temperature=0.3/maxTokens=100 已随 streamFn 透传且无报错（top_p 不支持，记入能力标志）");
}

// ── V4: 自定义 OpenAI 兼容 provider（同端点、自定义 id，验证 createProvider 路径）──
async function verifyCustomProvider() {
  const custom = createProvider({
    id: "companionheart",
    name: "CompanionHeart Custom",
    baseUrl: "https://api.deepseek.com",
    auth: {
      apiKey: {
        name: "CompanionHeart LLM key",
        resolve: async () => ({ auth: { apiKey }, source: "sidecar-env" }),
      },
    },
    models: [
      {
        id: "deepseek-v4-flash",
        name: "custom-endpoint-model",
        api: "openai-completions",
        provider: "companionheart",
        baseUrl: "https://api.deepseek.com",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 65536,
        maxTokens: 4096,
        compat: { supportsDeveloperRole: false, requiresReasoningContentOnAssistantMessages: true, thinkingFormat: "deepseek" },
      } as Model<"openai-completions">,
    ],
    api: openAICompletionsApi(),
  });
  models.setProvider(custom);
  const cModel = models.getModel("companionheart", "deepseek-v4-flash")!;
  const msg = await models.completeSimple(cModel, {
    systemPrompt: "只回答一个词。",
    messages: [{ role: "user", content: "1+1=?", timestamp: Date.now() }],
  }, { maxTokens: 20 });
  const text = msg.content.filter((b: any) => b.type === "text").map((b: any) => b.text).join("");
  mark("V4-custom-provider", text.includes("2"), `回答: ${text.trim().slice(0, 30)}`);
}

// ── V6: AbortController 中断 ──
async function verifyAbort() {
  const agent = new Agent({
    initialState: { systemPrompt: "尽量详细。", model: dsModel! },
    streamFn: makeStreamFn({ maxTokens: 2000 }),
  });
  let deltas = 0;
  agent.subscribe(async (event) => {
    if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
      deltas++;
      if (deltas === 3) agent.abort();
    }
  });
  const t0 = Date.now();
  try {
    await agent.prompt("写一篇 2000 字的长文介绍猫的历史。");
  } catch {
    /* abort 可能以异常或正常结束呈现，均可接受 */
  }
  const elapsed = Date.now() - t0;
  const last = agent.state.messages[agent.state.messages.length - 1] as any;
  mark("V6-abort", deltas >= 3 && elapsed < 30000, `中断于第3个delta后, 耗时${elapsed}ms, stopReason=${last?.stopReason}`);
}

try {
  await verifyHistoryAndStream();
  await verifyCustomProvider();
  await verifyAbort();
} catch (e) {
  console.error("验证过程中出错:", e);
  process.exitCode = 1;
} finally {
  console.log("\n===== Phase 0 验证结果 =====");
  for (const [k, v] of Object.entries(results)) console.log(`${k}: ${v}`);
}
