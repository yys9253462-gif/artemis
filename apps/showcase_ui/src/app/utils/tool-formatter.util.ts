/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { ActionParam } from '../core/models/stream.model';
import { extractNumbersFromCoordinateValue, isPureDirectionString, parseSequenceCoordinates } from './image-overlay.util';

// Tool objects are replaced (not mutated) when a trace is updated, so a
// WeakMap keyed on the tool is a safe memo for the parsed-args lookup that
// templates would otherwise re-run (including JSON.parse) on every render.
const toolArgsCache = new WeakMap<object, any>();

/**
 * Extract arguments from tool payload or direct args field
 */
export function getToolArgs(tool: any): any {
  if (!tool) return {};
  if (typeof tool === 'object') {
    const cached = toolArgsCache.get(tool);
    if (cached !== undefined) return cached;
    const args = computeToolArgs(tool);
    toolArgsCache.set(tool, args);
    return args;
  }
  return computeToolArgs(tool);
}

function computeToolArgs(tool: any): any {
  if (tool.payload) {
    let payloadObj = tool.payload;
    if (typeof payloadObj === 'string') {
      try { payloadObj = JSON.parse(payloadObj); } catch {}
    }
    if (payloadObj && typeof payloadObj === 'object') {
      if (payloadObj.args && typeof payloadObj.args === 'object') {
        return payloadObj.args;
      }
      return payloadObj;
    }
  }
  if (tool.args) {
    let argsObj = tool.args;
    if (typeof argsObj === 'string') {
      try { argsObj = JSON.parse(argsObj); } catch {}
    }
    if (argsObj && typeof argsObj === 'object') {
      return argsObj;
    }
  }
  return {};
}

/**
 * Check if a tool is one of the five note-related tools
 */
export function isNoteTool(tool: any): boolean {
  if (!tool || !tool.name) return false;
  const cleanName = tool.name.replace(/^(_)?(self\.)?exec_/, '');
  const nameLower = cleanName.toLowerCase();
  return ['save_note', 'read_note', 'list_notes', 'update_note', 'append_note'].includes(nameLower);
}

/**
 * Check if a tool is video analysis related
 */
export function isVideoTool(tool: any): boolean {
  if (!tool || !tool.name) return false;
  const cleanName = tool.name.replace(/^(_)?(self\.)?exec_/, '');
  const nameLower = cleanName.toLowerCase();
  return [
    'video_analysis',
    'video_analyzer',
    'video_analyzer_pure',
    'spawn_sub_agent',
    'analyze_audio_only'
  ].includes(nameLower);
}

export type VideoAnalysisOutcome = 'running' | 'recovering' | 'waiting' | 'complete' | 'partial' | 'failed';

export interface VideoAnalysisRange {
  start: number;
  end: number;
  category?: string;
  retryable?: boolean;
}

export interface VideoAnalysisView {
  outcome: VideoAnalysisOutcome;
  title: string;
  query: string;
  summary: string;
  reuse: 'none' | 'partial' | 'full';
  requestedRange: VideoAnalysisRange | null;
  completedRanges: VideoAnalysisRange[];
  failedRanges: VideoAnalysisRange[];
  evidenceCount: number;
  completedCount: number;
  totalCount: number;
  fallbackUsed: boolean;
}

function numericRange(value: any): VideoAnalysisRange | null {
  if (!value || typeof value !== 'object') return null;
  const start = Number(value.start);
  const end = Number(value.end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  return {
    start,
    end,
    category: value.category ? String(value.category) : undefined,
    retryable: value.retryable === true
  };
}

function parseVideoResultText(text: string): Partial<VideoAnalysisView> {
  const value = text.trim();
  if (!value) return {};
  if (value.startsWith('CACHED VIDEO ANALYSIS:')) {
    return { outcome: 'complete', reuse: 'full', summary: value.replace(/^CACHED VIDEO ANALYSIS:\s*/, '') };
  }
  if (value.startsWith('PARTIAL VIDEO ANALYSIS')) {
    return { outcome: 'partial', reuse: 'partial', summary: value };
  }
  if (value.startsWith('All sub-agent chunks failed') || value.startsWith('Error:')) {
    return { outcome: 'failed', summary: value };
  }
  if (value.includes('Analysis is already in progress in another video agent')) {
    return { outcome: 'waiting', summary: '已有另一个视频分析智能体正在分析该段证据。' };
  }
  return { outcome: 'complete', summary: value };
}

/** Build the user-facing, backward-compatible video analysis state. */
export function getVideoAnalysisView(tool: any): VideoAnalysisView | null {
  if (!isVideoTool(tool)) return null;
  const args = getToolArgs(tool);
  const payload = tool?.payload && typeof tool.payload === 'object' ? tool.payload : {};
  const rawResult = payload.result ?? tool.result ?? null;
  const structured = rawResult && typeof rawResult === 'object' ? rawResult : {};
  const parsed = typeof rawResult === 'string' ? parseVideoResultText(rawResult) : {};

  let outcome = String(structured.outcome || payload.outcome || parsed.outcome || '').toLowerCase() as VideoAnalysisOutcome;
  if (!['running', 'recovering', 'waiting', 'complete', 'partial', 'failed'].includes(outcome)) {
    outcome = tool?.status === 'failed' || tool?.status === 'error'
      ? 'failed'
      : tool?.status === 'running' ? 'running' : 'complete';
  }
  const recovering = structured.recovering === true || structured.fallback_used === true;
  if (outcome === 'running' && recovering) outcome = 'recovering';

  const start = Number(args.start_time ?? structured.requested_range?.start);
  const end = Number(args.end_time ?? structured.requested_range?.end);
  const requestedRange = Number.isFinite(start) && Number.isFinite(end) && end > start
    ? { start, end }
    : numericRange(structured.requested_range);
  const completedRanges = Array.isArray(structured.completed_ranges)
    ? structured.completed_ranges.map(numericRange).filter((range: VideoAnalysisRange | null): range is VideoAnalysisRange => Boolean(range))
    : [];
  const failedRanges = Array.isArray(structured.failed_ranges)
    ? structured.failed_ranges.map(numericRange).filter((range: VideoAnalysisRange | null): range is VideoAnalysisRange => Boolean(range))
    : [];
  const completedCount = Number(structured.completed_count ?? completedRanges.length ?? 0);
  const totalCount = Number(structured.total_count ?? (completedRanges.length + failedRanges.length));
  const titleByOutcome: Record<VideoAnalysisOutcome, string> = {
    running: '正在分析屏幕录制视频',
    recovering: '正在分析未完成的录制片段',
    waiting: '等待已有的视频分析完成',
    complete: structured.reuse === 'full' || parsed.reuse === 'full'
      ? '已复用既有视频分析结果'
      : '已完成屏幕录制视频分析',
    partial: '视频分析部分完成',
    failed: '视频分析未返回任何结果'
  };

  return {
    outcome,
    title: titleByOutcome[outcome],
    query: String(args.specific_query || args.query || args.prompt || structured.query || ''),
    summary: String(structured.summary || parsed.summary || ''),
    reuse: (structured.reuse || parsed.reuse || 'none') as 'none' | 'partial' | 'full',
    requestedRange,
    completedRanges,
    failedRanges,
    evidenceCount: Number(structured.evidence_count || 0),
    completedCount: Number.isFinite(completedCount) ? completedCount : 0,
    totalCount: Number.isFinite(totalCount) ? totalCount : 0,
    fallbackUsed: structured.fallback_used === true
  };
}

export function formatVideoTime(seconds: number): string {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/**
 * Extract target video filename or description for video analysis tools
 */
export function getVideoToolTarget(tool: any): string | null {
  if (!tool) return null;
  const args = getToolArgs(tool);
  if (args.video_path || args.video_file || args.file_path || args.file) {
    const p = String(args.video_path || args.video_file || args.file_path || args.file);
    return p.split('/').pop() || p;
  }
  if (args.time_description) {
    return String(args.time_description);
  }
  if (args.start_time !== undefined || args.end_time !== undefined) {
    const start = args.start_time ?? 0;
    const end = args.end_time ? `${args.end_time}s` : 'end';
    return `${start}s - ${end}`;
  }
  if (args.purpose) {
    return String(args.purpose);
  }
  return 'screen_record.mp4';
}

/**
 * Canonical list of mobile device automation and ADB command tool names.
 */
export const DEVICE_ACTION_TOOL_NAMES = new Set([
  'click', 'click_sequence', 'long_press', 'long_press_on', 'input', 'input_text', 
  'swipe', 'scroll', 'press_key', 'press_home', 'press_back', 'launch_app', 'manage_app', 'open_app',
  'focus_and_input_text', 'focus_and_clear_text', 'tap', 'wait_for_delay', 'wait',
  'run_adb_command', 'run_short_adb_command'
]);

/**
 * Check if a tool represents a real mobile device action or ADB command.
 */
export function isDeviceActionTool(tool: any): boolean {
  if (!tool || !tool.name) return false;
  if (tool.type === 'llm_call') return false;
  const cleanName = tool.name.replace(/^(_)?(self\.)?exec_/, '').toLowerCase();
  return DEVICE_ACTION_TOOL_NAMES.has(cleanName);
}

/**
 * Backward-compatible alias for isDeviceActionTool.
 */
export function isFailureAnalyzerActionTool(tool: any): boolean {
  return isDeviceActionTool(tool);
}

/**
 * Framework-internal infrastructure tools that are not intended for end-user timeline display.
 */
export function isInternalPlumbingTool(tool: any): boolean {
  if (!tool || !tool.name) return true;
  const cleanName = tool.name.replace(/^(_)?(self\.)?exec_/, '').toLowerCase();
  if (cleanName.includes('safety_net')) return true;
  if (cleanName === 'report_task_status' || cleanName === 'report_status' || cleanName === 'submit_task_status') {
    return true;
  }
  return false;
}

/**
 * Determines whether a tool invocation should be displayed in the timeline.
 */
export function shouldShowTool(tool: any, _stepData?: any): boolean {
  if (!tool || !tool.name) return false;
  if (tool.type === 'llm_call') return false;
  if (tool.type === 'agent') return false;
  if (tool.type === 'log') return false; // system notes render as quiet rows, not tool cards
  if (isInternalPlumbingTool(tool)) return false;

  return true;
}

/**
 * Extracts human-readable initiating agent name / role for a tool.
 */
export function getToolAgentName(tool: any): string | null {
  if (!tool) return null;
  const name = (tool.agent_name || tool.agent || '').toLowerCase();
  if (name.includes('failure') || name.includes('analyzer')) {
    return null; // Omit self-healing label per user instruction
  }
  if (name.includes('outputter')) {
    return '输出整理器';
  }
  if (name.includes('validator')) {
    return '校验器';
  }
  if (name.includes('diagnos')) {
    return '诊断器';
  }
  if (name.includes('explorer')) {
    return '元素定位器';
  }
  return null;
}

/**
 * Filter out nested child wrapper duplicates while preserving independent executions at the same level
 */
export function getUniqueGenericTools(tools: any[] | undefined): any[] {
  if (!tools) return [];

  // Only Google GenAI SDK retries are observable. Artemis wrapper retries and
  // opaque provider retries must never be presented as provider internals.
  const retryTools = tools.filter(tool =>
    tool?.type === 'llm_call'
    && tool?.status === 'retrying'
    && (tool?.name === 'llm_retry' || tool?.name === 'llm_retry_group')
    && tool?.payload?.source === 'provider_sdk'
    && ['google', 'gemini'].includes(String(tool?.payload?.provider || '').toLowerCase())
  );
  const retryKey = (tool: any) => String(
    tool?.payload?.request_id || `legacy-${tool?.step_id || 'unassigned'}`
  );
  const retryGroups = new Map<string, any[]>();
  for (const retry of retryTools) {
    const key = retryKey(retry);
    retryGroups.set(key, [...(retryGroups.get(key) || []), retry]);
  }
  const terminalRequestIds = new Set(
    tools
      .filter(tool => tool?.type === 'llm_call' && tool?.status === 'failed')
      .map(tool => tool?.payload?.request_id)
      .filter((requestId): requestId is string => typeof requestId === 'string' && !!requestId)
  );

  const buildRetryAggregate = (group: any[]) => {
    const firstRetry = group[0];
    const latestRetry = group[group.length - 1];
    return {
      ...firstRetry,
      trace_id: `llm-retry-group-${firstRetry?.payload?.request_id || firstRetry?.trace_id || firstRetry?.timestamp || 'unknown'}`,
      name: 'llm_retry_group',
      payload: {
        ...(latestRetry?.payload || {}),
        retry_count: group.length,
        total_delay: group.reduce(
          (total, retry) => total + (Number(retry?.payload?.delay) || 0),
          0
        ),
        retries: group.map(retry => ({
          trace_id: retry.trace_id,
          timestamp: retry.timestamp,
          error: retry?.payload?.error || retry.error,
          delay: Number(retry?.payload?.delay) || 0,
          provider: retry?.payload?.provider,
          source: retry?.payload?.source,
          request_id: retry?.payload?.request_id,
          scheduled_at: retry?.payload?.scheduled_at
        }))
      }
    };
  };

  const toolMap = new Map<string, any>();
  for (const t of tools) {
    if (t && t.trace_id) {
      toolMap.set(t.trace_id, t);
    }
  }

  const cleanName = (nameStr: string) => (nameStr || '').replace(/^(_)?(self\.)?exec_/, '').toLowerCase().trim();

  const result: any[] = [];
  const seenTraces = new Set<string>();
  const addedRetryGroups = new Set<string>();

  for (const tool of tools) {
    if (!tool || !tool.name) continue;
    if (tool.type === 'agent') continue;

    if (tool.type === 'llm_call' && tool.status === 'retrying') {
      const groupKey = retryKey(tool);
      const group = retryGroups.get(groupKey);
      const requestId = tool?.payload?.request_id;
      if (
        group
        && !addedRetryGroups.has(groupKey)
        && !(requestId && terminalRequestIds.has(requestId))
      ) {
        result.push(buildRetryAggregate(group));
        addedRetryGroups.add(groupKey);
      }
      continue;
    }

    if (tool.type === 'llm_call' && tool.status === 'failed') {
      // Callback-level attempt errors are implementation details. The wrapper
      // emits one terminal llm_pause trace after retries are exhausted.
      if (tool.name === 'llm_pause' || tool?.payload?.pause === true) {
        result.push(tool);
      }
      continue;
    }

    const currClean = cleanName(tool.name);

    // Check if this tool is a nested child execution of a parent tool with the exact same tool name
    let isNestedChildDuplicate = false;
    if (tool.parent_trace_id) {
      const parentTool = toolMap.get(tool.parent_trace_id);
      if (parentTool && cleanName(parentTool.name) === currClean) {
        isNestedChildDuplicate = true;
      }
    }

    if (!isNestedChildDuplicate) {
      if (tool.trace_id) {
        if (!seenTraces.has(tool.trace_id)) {
          seenTraces.add(tool.trace_id);
          // Always use the latest state from toolMap for this trace_id
          result.push(toolMap.get(tool.trace_id) || tool);
        }
      } else {
        result.push(tool);
      }
    }
  }
  return collapseVideoAnalysisTools(result);
}

/**
 * Present one note-style timeline row for one video-analyzer execution. Child
 * chunk, audio, and wrapper traces stay available in the raw trace but do not
 * look like repeated user-visible analyses.
 */
function collapseVideoAnalysisTools(tools: any[]): any[] {
  const groups = new Map<string, { firstIndex: number; tools: any[] }>();
  const passthrough: Array<{ index: number; tool: any }> = [];

  tools.forEach((tool, index) => {
    if (!isVideoTool(tool)) {
      passthrough.push({ index, tool });
      return;
    }
    const cleanName = String(tool.name || '').replace(/^(_)?(self\.)?exec_/, '').toLowerCase();
    const groupId = cleanName === 'video_analyzer' || cleanName === 'video_analyzer_pure'
      ? String(tool.trace_id || tool.parent_trace_id || `video-${index}`)
      : String(tool.parent_trace_id || tool.trace_id || `video-${index}`);
    const existing = groups.get(groupId);
    if (existing) {
      existing.tools.push(tool);
    } else {
      groups.set(groupId, { firstIndex: index, tools: [tool] });
    }
  });

  const collapsed = [...passthrough];
  for (const [groupId, group] of groups) {
    const views = group.tools
      .map(getVideoAnalysisView)
      .filter((view): view is VideoAnalysisView => Boolean(view));
    if (!views.length) continue;

    const hasActive = views.some(view => view.outcome === 'running' || view.outcome === 'recovering');
    const completed = views.filter(view => view.outcome === 'complete');
    const hasPartial = views.some(view => view.outcome === 'partial');
    const failed = views.filter(view => view.outcome === 'failed');
    const waiting = views.filter(view => view.outcome === 'waiting');
    let outcome: VideoAnalysisOutcome;
    if (hasActive) {
      outcome = views.some(view => view.outcome === 'recovering') ? 'recovering' : 'running';
    } else if (hasPartial || (completed.length > 0 && failed.length > 0)) {
      outcome = 'partial';
    } else if (completed.length > 0) {
      outcome = 'complete';
    } else if (waiting.length > 0) {
      outcome = 'waiting';
    } else {
      outcome = 'failed';
    }

    const ranges = views
      .map(view => view.requestedRange)
      .filter((range): range is VideoAnalysisRange => Boolean(range));
    const requestedRange = ranges.length
      ? {
          start: Math.min(...ranges.map(range => range.start)),
          end: Math.max(...ranges.map(range => range.end))
        }
      : null;
    const reuse = completed.length > 0 && completed.every(view => view.reuse === 'full')
      ? 'full'
      : views.some(view => view.reuse !== 'none') ? 'partial' : 'none';
    const base = group.tools[0];
    const structuredResult = {
      outcome,
      reuse,
      requested_range: requestedRange,
      completed_count: completed.length,
      total_count: views.length,
      evidence_count: views.reduce((sum, view) => sum + view.evidenceCount, 0),
      query: views.find(view => view.query)?.query || '',
      recovering: outcome === 'recovering',
      fallback_used: views.some(view => view.fallbackUsed)
    };

    collapsed.push({
      index: group.firstIndex,
      tool: {
        ...base,
        trace_id: `video-analysis-${groupId}`,
        name: 'video_analysis',
        status: outcome === 'running' || outcome === 'recovering' ? 'running' : 'success',
        payload: {
          ...(base.payload || {}),
          args: {
            ...(base.payload?.args || base.args || {}),
            start_time: requestedRange?.start,
            end_time: requestedRange?.end
          },
          result: structuredResult
        }
      }
    });
  }

  collapsed.sort((a, b) => a.index - b.index);
  return collapsed.map(item => item.tool);
}

/**
 * Get note key for the tool if it exists
 */
export function getToolKey(tool: any): string | null {
  if (!tool || !tool.name) return null;
  const args = tool.payload?.args || tool.args;
  const key = args?.key;
  if (!key) return null;
  return key.toLowerCase().endsWith('.md') ? key : `${key}.md`;
}

/**
 * Get display label for tools (e.g. for pills or headers)
 */
export function getToolDisplayLabel(tool: any, isFirstSaveNote: boolean = false): string {
  if (!tool || !tool.name) return '';
  const cleanName = tool.name.replace(/^(_)?exec_/, '');
  const nameLower = cleanName.toLowerCase();
  const args = getToolArgs(tool);

  switch (nameLower) {
    case 'manage_app':
    case 'launch_app': {
      const rawApp = args.app_name || args.package_name || args.app || '';
      const app = rawApp || '应用';
      const rawAction = args.action ? String(args.action).toLowerCase() : '';
      const verb = rawAction === 'launch' ? '正在启动' : (rawAction === 'stop' || rawAction === 'close' ? '正在停止' : '正在管理');
      return `${verb} "${app}"`;
    }

    case 'wait_for_delay':
    case 'wait_delay':
    case 'wait': {
      const delay = args.delay_seconds || args.seconds || args.delay || args.duration;
      return delay ? `等待 ${delay} 秒...` : '正在等待延时...';
    }
    case 'wait_for_text': {
      const text = args.text || args.target_text || '';
      return text ? `等待文本「${text}」出现在屏幕上` : '等待屏幕上出现指定文本';
    }

    case 'input_text':
    case 'input': {
      const text = args.text || args.input_text || '';
      return text ? `正在向输入框输入文本「${text}」` : '正在向输入框输入文本';
    }
    case 'focus_and_input_text': {
      const text = args.text || args.input_text || '';
      return text ? `正在聚焦输入框并输入「${text}」` : '正在聚焦输入框并输入文本';
    }
    case 'focus_and_clear_text':
      return '聚焦输入框并清空原有文本';

    case 'click':
    case 'tap': {
      const target = args.target_text || args.text || args.query || '';
      return target ? `点击「${target}」` : '点击屏幕元素';
    }
    case 'click_sequence':
      return '执行连续点击序列';
    case 'long_press': {
      const target = args.target_text || args.text || '';
      return target ? `长按「${target}」` : '长按屏幕元素';
    }
    case 'swipe': {
      const dir = args.action || args.direction || '';
      return dir ? `在屏幕上向 ${String(dir).toUpperCase()} 方向滑动` : '滑动屏幕';
    }
    case 'press_key': {
      const key = args.key || args.keycode || '';
      return key ? `按下按键 ${String(key).toUpperCase()}` : '按下物理按键';
    }

    case 'save_note':
      return isFirstSaveNote ? '创建笔记' : '保存笔记';
    case 'read_note':
      return '读取笔记';
    case 'list_notes':
      return '浏览全部已保存的笔记';
    case 'update_note':
      return '更新笔记';
    case 'append_note':
      return '更新笔记';

    case 'object_detection': {
      const q = Array.isArray(args.queries) ? args.queries.join(', ') : (args.queries || '');
      return q ? `在屏幕上定位: 「${q}」` : '在屏幕上定位界面元素';
    }
    case 'ask_explorer': {
      const query = args.query || args.prompt || '';
      return query ? `在屏幕上查找: 「${query}」` : '在屏幕上查找';
    }
    case 'report_failure_analysis': {
      const reason = args.reason || args.analysis || '';
      return reason ? `排查问题: ${reason}` : '排查执行异常问题';
    }
    case 'run_adb_command':
    case 'run_short_adb_command': {
      const cmd = args.command || args.cmd || '';
      return cmd ? `执行命令: ${cmd}` : '执行系统命令';
    }
    case 'search_logs':
    case 'read_logs': {
      const q = args.query || args.filter || '';
      return q ? `在日志中检索「${q}」` : '分析系统日志';
    }
    case 'log_analyzer':
    case 'output_analyzer':
      return '分析运行日志';
    case 'diagnoser':
    case 'diagnose':
      return '诊断异常问题';
    case 'video_analyzer':
    case 'video_analyzer_pure':
      return '分析屏幕录制视频';
    case 'extract_segment_metadata': {
      const start = args.start_time !== undefined ? `${args.start_time}s` : '';
      const end = args.end_time !== undefined ? `${args.end_time}s` : '';
      const range = (start && end) ? ` (${start} - ${end})` : (start ? ` (from ${start})` : '');
      return `裁剪屏幕录制片段${range}`;
    }
    case 'spawn_sub_agent': {
      const q = args.specific_query || args.query || args.prompt || '';
      return q ? `调用子智能体分析录屏: 「${q}」` : '调用子智能体分析录屏';
    }
    case 'analyze_audio_only': {
      const q = args.specific_query || args.query || '';
      return q ? `分析音频轨道: 「${q}」` : '分析录屏中的音频轨道';
    }
    case 'search_history': {
      const q = args.query || '';
      const range = Array.isArray(args.step_range) && args.step_range.length
        ? `（第 ${args.step_range[0]}–${args.step_range[args.step_range.length - 1]} 步）`
        : '';
      return q ? `在历史执行记录中检索「${q}」${range}` : `检索历史执行记录${range}`;
    }
    case 'replay_steps': {
      const n = args.start_step;
      const end = args.end_step;
      if (n !== undefined && n !== '' && end !== undefined && end !== null && end !== '' && String(end) !== String(n)) {
        return `回看第 ${n}–${end} 步`;
      }
      return n !== undefined && n !== '' ? `回看第 ${n} 步` : '回看步骤详情';
    }
    case 'get_step_screenshot': {
      const n = args.step_number;
      const variant = String(args.which || '').toLowerCase();
      if (variant === 'overlay') {
        return n !== undefined && n !== '' ? `查看第 ${n} 步动作的落点` : '查看动作落点';
      }
      const which = variant === 'post' ? '之后' : '之前';
      return n !== undefined && n !== '' ? `查看第 ${n} 步${which}的屏幕画面` : '查看某一步骤的屏幕截图';
    }
    case 'probe_device': {
      const kind = args.kind ? String(args.kind).replace(/_/g, ' ') : '';
      return kind ? `从设备读取 ${kind} 相关信息` : '读取设备状态';
    }
    case 'outputter':
    case 'output_synthesis':
      return '汇总生成输出报告';
    case 'web_search': {
      const q = args.query || '';
      return q ? `联网搜索「${q}」` : '联网搜索';
    }
    case 'read_url':
      return '抓取网页内容';
    case 'compress_history':
      return getCompressionLabel(tool);

    default:
      return `执行操作 ${cleanName}`;
  }
}

function formatTokenFigure(value: any): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return '';
  if (n < 1000) return `${Math.round(n)}`;
  return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`;
}

/** Format compression progress and token usage for the timeline. */
export function getCompressionLabel(tool: any): string {
  const args = getToolArgs(tool) || {};
  const start = Number(args.start_step);
  const end = Number(args.end_step);
  const hasRange = Number.isFinite(start) && Number.isFinite(end) && start > 0 && end > 0;
  const range = hasRange
    ? (start === end ? `第 ${start} 步` : `第 ${start}–${end} 步`)
    : '更早的步骤';
  const rangeCapitalized = range.charAt(0).toUpperCase() + range.slice(1);
  const status = String(tool?.status || '').toLowerCase();
  const phase = getCompressionPhase(tool);

  if (status === 'failed' || phase === 'failed') {
    return `暂时无法压缩${range}，已保留完整记录并稍后重试`;
  }
  if (status !== 'success') {
    const note = String(args.note || '').toLowerCase();
    if (note === 'retrying') return `正在重试${range}的记忆摘要…`;
    if (note === 'held' || phase === 'ready') {
      const swapAt = Number(args.swap_at_tokens);
      const heldContext = Number(args.context_tokens);
      const heldParts = [`${range}的简短记忆已就绪；在上下文占满前保留完整记录`];
      if (heldContext > 0 && swapAt > 0) {
        heldParts.push(`≈ ${formatTokenFigure(heldContext)} / ${formatTokenFigure(swapAt)} Token`);
      }
      return heldParts.join(' · ');
    }
    return `正在将${range}压缩为简短记忆以释放上下文…`;
  }

  const parts: string[] = [];
  const source = Number(args.source_tokens);
  const summary = Number(args.summary_tokens);
  if (args.forced) {
    parts.push(`${range}已压缩为摘要以释放记忆空间`);
  } else {
    parts.push(`${range}已压缩为简短记忆`);
    if (source > 0 && summary > 0) {
      const factor = source / summary;
      const factorText = factor >= 2 ? `（缩小至 ${Math.round(factor)} 倍）` : '';
      parts.push(`${formatTokenFigure(source)} → ${formatTokenFigure(summary)} Token${factorText}`);
    }
  }
  const context = Number(args.context_tokens);
  const budget = Number(args.context_budget);
  if (context > 0) {
    parts.push(budget > 0
      ? `工作记忆 ≈ ${formatTokenFigure(context)} / ${formatTokenFigure(budget)} Token`
      : `工作记忆 ≈ ${formatTokenFigure(context)} Token`);
  }
  return parts.join(' · ');
}

/**
 * Plain-language phases of one compress_history line. Mirrors
 * COMPRESSION_PHASES in artemis/memory/chunking.py: the backend writes
 * `args.phase`; the trace `status` (running/success/failed) is left alone.
 */
export type CompressionPhase = 'summarizing' | 'ready' | 'applied' | 'failed';

const COMPRESSION_PHASES: readonly CompressionPhase[] = ['summarizing', 'ready', 'applied', 'failed'];

export function isCompressionTool(tool: any): boolean {
  const name = String(tool?.name || '').toLowerCase().replace(/^(_)?exec_/, '');
  return name === 'compress_history';
}

/**
 * Phase of a compress_history line. Prefers the backend's `args.phase`;
 * older traces without it fall back to status + note (`held` ⇒ ready).
 */
export function getCompressionPhase(tool: any): CompressionPhase {
  const args = getToolArgs(tool) || {};
  const declared = String(args.phase || '').toLowerCase() as CompressionPhase;
  if (COMPRESSION_PHASES.includes(declared)) return declared;
  const status = String(tool?.status || '').toLowerCase();
  if (status === 'failed') return 'failed';
  if (status === 'success') return 'applied';
  if (String(args.note || '').toLowerCase() === 'held') return 'ready';
  return 'summarizing';
}

/** One short, non-technical label per compression phase. */
export function getCompressionPhaseLabel(tool: any): string {
  switch (getCompressionPhase(tool)) {
    case 'ready':
      return '摘要已就绪，待上下文占满时启用';
    case 'applied':
      return '该段记录已被其摘要替换';
    case 'failed':
      return '摘要生成失败，已保留完整记录';
    default:
      return '正在生成该段摘要';
  }
}

/**
 * A ready-but-held summary is waiting, not working: the card must not keep
 * its running pulse even though the trace status is still `running`.
 */
export function isCompressionWaiting(tool: any): boolean {
  return isCompressionTool(tool) && getCompressionPhase(tool) === 'ready';
}

/**
 * Get Material Symbol icon for tools
 */
export function getToolIcon(tool: any): string {
  if (!tool || !tool.name) return 'settings';
  const name = tool.name.toLowerCase().replace(/^(_)?exec_/, '');
  switch (name) {
    case 'click':
    case 'tap':
      return 'ads_click';
    case 'click_sequence':
    case 'long_press':
      return 'touch_app';
    case 'input_text':
    case 'input':
      return 'keyboard';
    case 'swipe':
      return 'swipe';
    case 'press_key':
      return 'keyboard_tab';
    case 'manage_app':
      return 'open_in_new';
    case 'wait_for_delay':
      return 'timer';
    case 'wait_for_text':
      return 'hourglass_empty';
    case 'object_detection':
      return 'search';
    case 'ask_explorer':
      return 'search';
    case 'report_failure_analysis':
      return 'assessment';
    case 'run_adb_command':
    case 'run_short_adb_command':
      return 'terminal';
    case 'web_search':
      return 'travel_explore';
    case 'read_url':
      return 'language';
    case 'search_logs':
    case 'read_logs':
    case 'log_analyzer':
    case 'output_analyzer':
      return 'receipt_long';
    case 'diagnoser':
    case 'diagnose':
      return 'medical_services';
    case 'video_analyzer':
    case 'video_analyzer_pure':
      return 'video_camera_back';
    case 'extract_segment_metadata':
      return 'crop';
    case 'spawn_sub_agent':
      return 'smart_toy';
    case 'analyze_audio_only':
      return 'graphic_eq';
    case 'search_history':
      return 'find_in_page';
    case 'replay_steps':
      return 'manage_search';
    case 'get_step_screenshot':
      return 'image_search';
    case 'probe_device':
      return 'sensors';
    case 'outputter':
    case 'output_synthesis':
      return 'assignment_turned_in';
    case 'compress_history':
      return 'compress';
    default:
      return 'build';
  }
}

/**
 * Get formatted title for a tool call card
 */
export function getToolTitle(tool: any): string {
  if (!tool || !tool.name) return '工具调用';
  const cleanName = tool.name.replace(/^(_)?exec_/, '');
  const name = cleanName.toLowerCase();
  switch (name) {
    case 'click':
    case 'tap':
      return '点击元素';
    case 'click_sequence':
      return '执行连续点击序列';
    case 'long_press':
      return '长按元素';
    case 'input_text':
    case 'input':
      return '输入文本';
    case 'swipe':
    case 'scroll': {
      const args = getToolArgs(tool);
      const dir = args.direction || args.gesture || (typeof args.action === 'string' ? args.action : '');
      if (dir && isPureDirectionString(dir)) return `滑动屏幕（${String(dir).toUpperCase()}）`;
      return '滑动屏幕';
    }
    case 'drag':
    case 'drag_and_drop':
      return '拖拽屏幕';
    case 'press_key':
      return '按下物理按键';
    case 'manage_app':
    case 'launch_app': {
      const args = getToolArgs(tool);
      const rawAction = args.action ? String(args.action).toLowerCase() : '';
      if (rawAction === 'launch') return '启动应用';
      if (rawAction === 'stop' || rawAction === 'close') return '停止应用';
      return '管理应用';
    }
    case 'wait_for_delay':
    case 'wait_delay':
      return '等待延时';
    case 'wait_for_text':
      return '等待指定文本出现';
    case 'object_detection':
      return '定位界面元素';
    case 'ask_explorer':
      return '在屏幕上查找';
    case 'report_failure_analysis':
      return '排查异常问题';
    case 'run_adb_command':
    case 'run_short_adb_command':
      return '执行系统命令';
    case 'web_search':
      return '联网搜索';
    case 'read_url':
      return '抓取网页内容';
    case 'search_logs':
    case 'read_logs':
      return '检索运行日志';
    case 'log_analyzer':
    case 'output_analyzer':
      return '分析运行日志';
    case 'diagnoser':
    case 'diagnose':
      return '诊断异常问题';
    case 'video_analyzer':
    case 'video_analyzer_pure':
      return '分析屏幕录制视频';
    case 'extract_segment_metadata':
      return '裁剪屏幕录制片段';
    case 'spawn_sub_agent':
      return '下发视频分析任务';
    case 'analyze_audio_only':
      return '分析音频轨道';
    default:
      return cleanName.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase());
  }
}

/**
 * Join per-point self-described targets (click_sequence `target_descriptions`)
 * into one label, chained with ' → ' like the coordinate rendering.
 * Returns '' when the value is missing or holds no usable text.
 */
export function joinTargetDescriptions(descriptions: any): string {
  if (!Array.isArray(descriptions)) return '';
  const parts = descriptions
    .map(d => (d === null || d === undefined) ? '' : String(d).trim())
    .filter(d => d.length > 0);
  return parts.join(' → ');
}

/**
 * Get target text description for tools
 */
export function getToolTargetText(tool: any): string {
  if (!tool || !tool.name) return '';
  const args = getToolArgs(tool);
  const name = tool.name.toLowerCase().replace(/^(_)?exec_/, '');
  if (name === 'manage_app' || name === 'launch_app') {
    const rawApp = args.app_name || args.package_name || args.app || '';
    const app = rawApp ? (rawApp.charAt(0).toUpperCase() + rawApp.slice(1)) : '';
    const rawAct = args.action ? String(args.action).toLowerCase() : '';
    const act = rawAct ? (rawAct.charAt(0).toUpperCase() + rawAct.slice(1)) : '';
    if (act && app) {
      return `${act} ${app}`;
    }
    return app || act || '';
  }
  if (name === 'swipe' && typeof args.action === 'string' && isPureDirectionString(args.action)) {
    return args.action;
  }
  if (name === 'wait_for_text') {
    return args.text || '';
  }
  if (name === 'object_detection') {
    if (Array.isArray(args.queries)) return args.queries.join(', ');
    return args.queries || '';
  }
  if (name === 'ask_explorer' || name === 'web_search') {
    return args.query || args.prompt || '';
  }
  if (name === 'read_url') {
    return args.url || '';
  }
  if (name === 'search_logs' || name === 'read_logs') {
    return args.query || args.filter || '';
  }
  if (name === 'report_failure_analysis') {
    return args.status || args.reason || args.analysis || '';
  }
  if (name === 'click_sequence' || name === 'tap_sequence') {
    // One self-described target per point, chained like getToolCoords does.
    const joined = joinTargetDescriptions(args.target_descriptions);
    if (joined) return joined;
  }
  if (args.target && typeof args.target === 'string') {
    return args.target;
  }
  if (args.target && typeof args.target === 'number') {
    return `元素 #${args.target}`;
  }
  if (args.index !== undefined) {
    return `元素 #${args.index}`;
  }
  return args.target_text || args.target_description || args.target_class || args.element || args.element_text || (name !== 'input_text' ? args.text : '') || '';
}

/**
 * Get input label for tools
 */
export function getToolInputLabel(tool: any): string {
  if (!tool || !tool.name) return '输入';
  const name = tool.name.toLowerCase().replace(/^(_)?exec_/, '');
  if (name === 'wait_for_delay' || name === 'wait_delay' || name === 'delay' || name === 'wait') {
    return '时长';
  }
  if (name === 'swipe' || name === 'scroll' || name === 'drag' || name === 'drag_and_drop') {
    const args = getToolArgs(tool);
    const dir = args.direction || args.gesture || (typeof args.action === 'string' ? args.action : '');
    if (dir && isPureDirectionString(dir)) {
      return '方向';
    }
    return '输入';
  }
  if (name === 'press_key' || name === 'press_home' || name === 'press_back') {
    return '按键';
  }
  if (name === 'input_text' || name === 'input') {
    return '输入文本';
  }
  return '输入';
}

/**
 * Get input value for tools
 */
export function getToolInputText(tool: any): string {
  if (!tool || !tool.name) return '';
  const args = getToolArgs(tool);
  const name = tool.name.toLowerCase().replace(/^(_)?exec_/, '');
  if (name === 'press_key') {
    return args.key || args.keycode || '';
  }
  if (name === 'swipe' || name === 'scroll' || name === 'drag' || name === 'drag_and_drop') {
    const dir = args.direction || args.gesture || (typeof args.action === 'string' ? args.action : '');
    if (dir && isPureDirectionString(dir)) {
      return String(dir).toUpperCase();
    }
    return '';
  }
  if (name === 'wait_for_delay' || name === 'wait_delay') {
    return args.time_in_ms ? `${args.time_in_ms}ms` : (args.delay_ms ? `${args.delay_ms}ms` : (args.time ? `${args.time}` : ''));
  }
  if (name === 'long_press' && args.duration) {
    return `时长: ${args.duration}ms`;
  }
  if (name === 'input_text' || name === 'input') {
    return args.text || args.input_text || '';
  }
  return args.input_text || '';
}

/**
 * Get coordinates string representation for tools
 */
export function getToolCoords(tool: any): string {
  if (!tool || !tool.name) return '';
  const args = getToolArgs(tool);
  const cleanName = tool.name.replace(/^(_)?exec_/, '');
  const name = cleanName.toLowerCase();

  // Check sequence first if action is sequence or sequence arg is present
  const isSequenceAction = name === 'click_sequence' || name === 'tap_sequence' || Boolean(args.sequence || args.normalized_sequence);
  const rawSeq = args.normalized_sequence || args.sequence || args.targets || (Array.isArray(args.coordinates) && Array.isArray(args.coordinates[0]) ? args.coordinates : null);
  const seqPoints = parseSequenceCoordinates(rawSeq);
  if (seqPoints && seqPoints.length > 0 && (isSequenceAction || seqPoints.length > 1)) {
    return seqPoints.map(pt => `[${pt[0]}, ${pt[1]}]`).join(' → ');
  }

  // Check normalized start and end first
  const normStart = extractNumbersFromCoordinateValue(args.normalized_start_coordinates || args.start_coordinates || args.start);
  const normEnd = extractNumbersFromCoordinateValue(args.normalized_end_coordinates || args.end_coordinates || args.end);
  if (normStart && normEnd && normStart.length === 2 && normEnd.length === 2) {
    return `[${normStart[0]}, ${normStart[1]}] → [${normEnd[0]}, ${normEnd[1]}]`;
  }

  const coords = extractNumbersFromCoordinateValue(args.normalized_coordinates) ||
                 extractNumbersFromCoordinateValue(args.coordinates) ||
                 extractNumbersFromCoordinateValue(args.target) ||
                 extractNumbersFromCoordinateValue(args.action) ||
                 extractNumbersFromCoordinateValue(args.gesture) ||
                 extractNumbersFromCoordinateValue(args.point);

  if (coords && Array.isArray(coords)) {
    if (coords.length === 4) {
      return `[${coords[0]}, ${coords[1]}] → [${coords[2]}, ${coords[3]}]`;
    }
    if (coords.length === 2) {
      return `[${coords[0]}, ${coords[1]}]`;
    }
    return coords.join(', ');
  }

  if (args.x !== undefined && args.y !== undefined) {
    return `[${args.x}, ${args.y}]`;
  }
  return '';
}

/**
 * Get analysis / reasoning text for tools
 */
export function getToolAnalysisText(tool: any): string {
  if (!tool || !tool.name) return '';
  const args = getToolArgs(tool);
  return args.analysis || args.reasoning || args.summary || '';
}

/**
 * Check if tool is ADB command
 */
export function isAdbCommandTool(tool: any): boolean {
  if (!tool || !tool.name) return false;
  const name = tool.name.toLowerCase().replace(/^(_)?exec_/, '');
  return name === 'run_adb_command' || name === 'run_short_adb_command';
}

/**
 * Get ADB command line string
 */
export function getAdbCommandLine(tool: any): string {
  const args = getToolArgs(tool);
  return args.CommandLine || '';
}

/**
 * Get ADB working directory
 */
export function getAdbCwd(tool: any): string {
  const args = getToolArgs(tool);
  return args.Cwd || '';
}

/**
 * Get ADB requested terminal id
 */
export function getAdbTerminalId(tool: any): string {
  const args = getToolArgs(tool);
  return args.RequestedTerminalID || '';
}

/**
 * Get fallback generic details for unspecified tools
 */
export function getToolGenericDetails(tool: any): string {
  if (!tool) return '';
  if (isAdbCommandTool(tool)) {
    return '';
  }
  if (getToolTargetText(tool) || getToolInputText(tool) || getToolCoords(tool) || getToolAnalysisText(tool)) {
    return '';
  }
  const args = getToolArgs(tool);
  if (!args || typeof args !== 'object') return '';
  const ignoredKeys = new Set(['state', 'controller', 'ctx', 'session_id', 'step_id', 'trace_id', 'parent_trace_id', 'times', 'delay_ms']);
  const entries = Object.entries(args).filter(([k, v]) => !ignoredKeys.has(k) && v !== undefined && v !== null && v !== '');
  if (entries.length === 0) return '';
  return entries.map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ');
}

/**
 * Check if tool execution failed
 */
export function isToolFailed(tool: any): boolean {
  if (!tool) return false;
  if (tool.status === 'failed' || tool.status === 'error') return true;
  const args = getToolArgs(tool);
  if (args.status === 'failed' || args.status === 'error' || args.status === 'cannot_fix') return true;
  return false;
}

/**
 * Get error message for a failed tool
 */
export function getToolErrorMessage(tool: any): string {
  if (!tool) return '工具执行失败';
  const args = getToolArgs(tool);
  if (args.status === 'cannot_fix') return '状态: 无法修复';
  if (args.error || args.message || args.failure_reason) {
    return args.error || args.message || args.failure_reason;
  }
  if (tool.error || tool.message) return tool.error || tool.message;
  return '动作执行失败';
}

/**
 * Extract extra parameters for generic tools
 */
export function extractToolExtraParams(toolData: any, cache?: WeakMap<any, ActionParam[]>): ActionParam[] {
  if (!toolData) return [];
  const payload = toolData.payload || toolData.args || toolData;
  if (!payload || typeof payload !== 'object') return [];
  if (cache && cache.has(payload)) {
    return cache.get(payload)!;
  }

  const standardKeys = new Set([
    'action', 'name', 'type', 'target_text', 'target_description', 'target_descriptions',
    'text', 'input_text', 'target',
    'coordinates', 'coords', 'target_bounds', 'bounds', 'target_resource_id',
    'resource_id', 'target_class', 'class_name', 'normalized_coordinates',
    'pre_image_name', 'post_image_name', 'pre_screenshot', 'post_screenshot',
    'before_screenshot', 'after_screenshot', 'status', 'success', 'timestamp',
    'created_at', 'start_time', 'execution_id', 'controller', 'agent', 'session_id', 'step_id',
    'app_name', 'package_name', 'app', 'key', 'keycode', 'time_in_ms', 'delay_ms', 'delay_seconds', 'duration',
    'args', 'kwargs', 'parameters', 'extra_params', 'payload', 'trace_id', 'result', 'error', 'analysis', 'details', 'command', 'cwd', 'terminal_id'
  ]);

  const result: ActionParam[] = [];

  const rawArgs = toolData.args || toolData.Args || toolData.kwargs || toolData.parameters || toolData.payload;
  let parsedArgs: any = {};
  if (rawArgs) {
    if (typeof rawArgs === 'object') {
      parsedArgs = rawArgs;
    } else if (typeof rawArgs === 'string') {
      try {
        parsedArgs = JSON.parse(rawArgs);
      } catch {
        if (!rawArgs.includes('<') && !rawArgs.includes('object at')) {
          parsedArgs = { details: rawArgs };
        }
      }
    }
  }

  const mergedObj = { ...toolData, ...(typeof payload === 'object' ? payload : {}), ...parsedArgs };

  for (const [k, v] of Object.entries(mergedObj)) {
    const lowerK = k.toLowerCase();
    if (standardKeys.has(lowerK)) continue;
    if (v === null || v === undefined || v === '') continue;

    let valStr = String(v);
    if (valStr.includes('object at 0x') || valStr.startsWith('<artemis.') || valStr.includes('<controller') || valStr.includes('<android_world')) continue;

    if (typeof v === 'object') {
      try { valStr = JSON.stringify(v); } catch { valStr = String(v); }
    }

    let prettyKey = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    if (lowerK === 'time_in_ms' || lowerK === 'delay_ms') prettyKey = 'Delay';

    result.push({ key: prettyKey, value: valStr });
  }

  if (cache) {
    cache.set(payload, result);
  }
  return result;
}

/**
 * Check if text is genuine human thinking rather than raw JSON payload output
 */
export function isHumanThinking(text: string | null): boolean {
  if (!text) return false;
  let trimmed = text.trim();
  if (!trimmed) return false;

  // Strip markdown code blocks if wrapped: ```json ... ``` or ``` ... ```
  if (trimmed.startsWith('```')) {
    const match = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
    if (match) {
      trimmed = match[1].trim();
    }
  }

  // Direct object or array start
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    return false;
  }

  // Try parsing as JSON if it looks like JSON structures
  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed === 'object' && parsed !== null) {
      return false;
    }
  } catch {
    // Not valid standalone JSON, continue checks
  }

  // Check for common JSON object detection / grounding / action / tool patterns
  if (/^\s*\{.*"label"\s*:.*"results"\s*:/s.test(trimmed) ||
      /^\s*\{.*"point"\s*:.*"label"\s*:/s.test(trimmed) ||
      /^\s*\{.*"action"\s*:/s.test(trimmed) ||
      /^\s*\{.*"name"\s*:/s.test(trimmed) ||
      /^\s*\{\s*"[^"]+"\s*:\s*/.test(trimmed) ||
      /^\s*\[\s*\{\s*"[^"]+"\s*:\s*/.test(trimmed)) {
    return false;
  }

  return true;
}

/**
 * Clean up raw error messages for display in the UI
 */
export function cleanErrorMessage(rawError: any): string {
  if (typeof rawError === 'object' && rawError !== null) {
    if (rawError.message && typeof rawError.message === 'string') {
      return cleanErrorMessage(rawError.message);
    }
    if (rawError.error?.message && typeof rawError.error?.message === 'string') {
      return cleanErrorMessage(rawError.error.message);
    }
    if (rawError.detail && typeof rawError.detail === 'string') {
      return cleanErrorMessage(rawError.detail);
    }
    try {
      return JSON.stringify(rawError);
    } catch {
      return String(rawError);
    }
  }

  const errorStr = String(rawError).trim();
  if (!errorStr) return '未知错误';

  // 1. Try regex extraction for "message": "..."
  const doubleQuoteMsgMatch = errorStr.match(/"message"\s*:\s*"((?:[^"\\]|\\.)*)"/i);
  if (doubleQuoteMsgMatch && doubleQuoteMsgMatch[1]) {
    const unescaped = doubleQuoteMsgMatch[1].replace(/\\"/g, '"').replace(/\\n/g, ' ').trim();
    if (unescaped) return unescaped;
  }

  // 2. Try regex extraction for 'message': '...'
  const singleQuoteMsgMatch = errorStr.match(/'message'\s*:\s*['"]((?:[^'\\]|\\.)*)['"]/i);
  if (singleQuoteMsgMatch && singleQuoteMsgMatch[1]) {
    const unescaped = singleQuoteMsgMatch[1].replace(/\\'/g, "'").replace(/\\n/g, ' ').trim();
    if (unescaped) return unescaped;
  }

  // 3. Try parsing JSON substrings inside the error string
  const jsonMatch = errorStr.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      const normalizedJsonStr = jsonMatch[0]
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null');
      const parsed = JSON.parse(normalizedJsonStr);
      if (parsed?.message) return String(parsed.message);
      if (parsed?.error?.message) return String(parsed.error.message);
    } catch {
      // Ignore
    }
  }

  // 4. Fallback: truncate at trace dump headers or return clean message
  let fallback = errorStr;
  if (fallback.includes('=== Source Location Trace')) {
    fallback = fallback.split('=== Source Location Trace')[0];
  }
  if (fallback.includes('[type.googleapis.com')) {
    fallback = fallback.split('[type.googleapis.com')[0];
  }
  fallback = fallback
    .replace(/^Pre-execution validation failed:\s*/i, '')
    .replace(/^Pixel-level validation failed:\s*/i, '')
    .replace(/^Execution error:\s*/i, '')
    .replace(/^ServerError:\s*/i, '')
    // LLM wrappers may add this prefix more than once. It is context, not the
    // actual provider reason, and an empty prefix must not be shown as though
    // it were a useful error message.
    .replace(/^(?:LLM\s+(?:Request\s+)?Error\s*:\s*)+/i, '')
    .trim();

  return fallback || '未知错误';
}
