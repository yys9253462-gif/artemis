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

/**
 * Launcher options for `/api/run` (`verification_level`, `explorer_mode`).
 * Keep ids in sync with `VERIFICATION_LEVEL_PRESETS` in `artemis/config/agent.py`
 * and `EXPLORER_TIERS` in `artemis/agents/explorer/tiers.py`.
 */

export type VerificationLevelId = 'off' | 'final' | 'checkpoints' | 'strict';
export type ExplorerModeId = 'flash' | 'pro' | 'ultra';

/** One notch on a tuning slider. */
export interface TuningLevel<TId extends string = string> {
  /** Wire value sent to the backend. */
  id: TId;
  /** Short name shown next to the slider title and as the hover card heading. */
  label: string;
  /** One-sentence summary shown in the hover card. */
  tagline: string;
  /** Plain-language time cost, e.g. "no extra time". */
  latency: string;
  /** Checks or searches performed at this level. */
  runs: string[];
  /** Checks or searches omitted at this level. */
  skips?: string[];
  /** When to pick this level. */
  bestFor: string;
}

export const VERIFICATION_LEVELS: readonly TuningLevel<VerificationLevelId>[] = [
  {
    id: 'off',
    label: '关闭',
    tagline: '不做任何校验：任务看起来完成即立即结束。',
    latency: '不增加额外耗时',
    runs: [
      '每执行完一个步骤即视为完成。',
      '你会获得完整的动作轨迹，但没有通过 / 失败的判定结论。'
    ],
    skips: ['不进行任何二次核对，也不进行任何重试。'],
    bestFor: '快速尝试与功能演示，只想观察执行过程时使用。'
  },
  {
    id: 'final',
    label: '任务结束时',
    tagline: '任务结束后，对最终结果与你的目标做一次校验。这是默认档位。',
    latency: '在结尾增加约 20–60 秒',
    runs: [
      '任务结束时，会比对最终屏幕画面、步骤历史与设备状态是否与你的要求一致。',
      '若结果不符，任务会回退并尝试修复，最多 3 次。'
    ],
    skips: ['任务运行过程中不做任何中间校验。'],
    bestFor: '日常常规任务：在几乎不拖慢速度的前提下，得到诚实的通过 / 失败结论。'
  },
  {
    id: 'checkpoints',
    label: '每一步',
    tagline: '每个步骤完成后立即校验，并在结尾再做一次最终校验。',
    latency: '每步之后有一次短校验，在后台执行',
    runs: [
      '每个步骤完成后会立刻用当时的截图进行校验。',
      '如果某步出错，会先修复再继续（每步最多 2 次尝试）。',
      '未通过的测试条件会被记录下来，任务继续执行。',
      '结尾仍会执行最终校验。'
    ],
    bestFor: '长流程任务：早期一个错误若不及时纠正，会毁掉后续全部工作。'
  },
  {
    id: 'strict',
    label: '严格模式',
    tagline: '每个步骤都校验，且重试次数更多。首个测试失败立即终止任务。',
    latency: '最慢：校验更多、重试更多',
    runs: [
      '每次校验耗时更长、尝试次数更多：每步最多 4 次修复，结尾最多 5 次。',
      '首个失败的测试条件会立即终止任务，并附带完整证据。'
    ],
    bestFor: '发布前验收与回归测试，绝不容忍错误的通过结论。'
  }
];

export const EXPLORER_MODES: readonly TuningLevel<ExplorerModeId>[] = [
  {
    id: 'flash',
    label: '快速一瞥',
    tagline: '一眼扫过即可定位屏幕上的按钮与文字。',
    latency: '每次查找 1 次感知',
    runs: [
      '按名称、图标或颜色查找屏幕上的元素，并立即返回其位置坐标。',
      '可同时查找多个元素。'
    ],
    skips: ['不做局部放大，也不做二次尝试。'],
    bestFor: '按钮、图标与文字标注清晰的普通 App。'
  },
  {
    id: 'pro',
    label: '二次确认',
    tagline: '最多感知 3 次，中间进行推理，再给出答案。',
    latency: '每次查找最多 3 次感知',
    runs: [
      '先读取屏幕层级结构，再对画面进行搜索。',
      '若首次未命中，会在 3 次感知内换用其它策略重新查找。'
    ],
    skips: ['仍不做小区域放大，以保持查找速度。'],
    bestFor: '以相对位置描述的控件（如「Wi-Fi 旁边的开关」）或标注不清晰的元素。'
  },
  {
    id: 'ultra',
    label: '局部放大',
    tagline: '对屏幕局部进行放大裁剪，最多感知 8 次。',
    latency: '每次查找最多 8 次感知（最慢）',
    runs: [
      '可裁剪并放大屏幕局部，逐块阅读微小文字与密集排版。',
      '后续感知会复用前次结果，因此实际耗时比听起来更少。'
    ],
    bestFor: '元素密集的界面、极小的目标、图表与手绘内容，以及对精确位置要求极高的校验。'
  }
];

/** Per-run tuning sent with `/api/run` for the Pro profile. */
export interface ProTuningOptions {
  verificationLevel?: VerificationLevelId | string;
  explorerMode?: ExplorerModeId | string;
}

/** Effective defaults reported by `GET /api/run/defaults`. */
export interface ProTuningDefaults {
  verification_level?: string | null;
  explorer_mode?: string | null;
}

export const DEFAULT_VERIFICATION_LEVEL: VerificationLevelId = 'final';
export const DEFAULT_EXPLORER_MODE: ExplorerModeId = 'flash';

/** Index of a level id within its ladder; falls back to the default when unknown. */
export function levelIndex<TId extends string>(
  ladder: readonly TuningLevel<TId>[],
  id: string | null | undefined,
  fallback: TId
): number {
  const wanted = String(id ?? '').trim().toLowerCase();
  const idx = ladder.findIndex((l) => l.id === wanted);
  if (idx >= 0) return idx;
  return Math.max(0, ladder.findIndex((l) => l.id === fallback));
}

/** Slider fill percentage for a notch index on a ladder of `count` notches. */
export function notchPercent(index: number, count: number): number {
  if (count <= 1) return 0;
  const clamped = Math.min(Math.max(index, 0), count - 1);
  return (clamped / (count - 1)) * 100;
}
