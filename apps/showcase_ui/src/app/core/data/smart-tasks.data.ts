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

export interface AppReference {
  name: string;
  icon: string;
  pkg?: string;
  category?: string;
}

export type SuggestionCategory =
  | 'all'
  | 'flash'
  | 'pro'
  | 'cross_app'
  | 'monitor';

export interface SmartSuggestion {
  id: string;
  title: string;
  description: string;
  goal: string;
  profile: 'flash' | 'pro';
  category: 'flash' | 'pro' | 'cross_app' | 'monitor';
  tag: string;
  apps: AppReference[];
  requiredPackages?: string[];
  matchMode?: 'any' | 'all';
  priority?: number;
}

/**
 * Recognized Android App Package Registry
 */
export const APP_REGISTRY: Record<string, AppReference> = {
  // Google Suite & System
  'com.google.android.apps.maps': { name: '谷歌地图', icon: 'explore', pkg: 'com.google.android.apps.maps', category: 'navigation' },
  'com.google.android.gm': { name: 'Gmail', icon: 'mail', pkg: 'com.google.android.gm', category: 'productivity' },
  'com.android.chrome': { name: 'Chrome 浏览器', icon: 'public', pkg: 'com.android.chrome', category: 'browser' },
  'com.google.android.youtube': { name: 'YouTube', icon: 'smart_display', pkg: 'com.google.android.youtube', category: 'entertainment' },
  'com.android.settings': { name: '系统设置', icon: 'settings', pkg: 'com.android.settings', category: 'system' },
  'com.google.android.deskclock': { name: '时钟', icon: 'timer', pkg: 'com.google.android.deskclock', category: 'utility' },
  'com.android.deskclock': { name: '时钟', icon: 'timer', pkg: 'com.android.deskclock', category: 'utility' },
  'com.google.android.calculator': { name: '计算器', icon: 'calculate', pkg: 'com.google.android.calculator', category: 'utility' },
  'com.android.calculator2': { name: '计算器', icon: 'calculate', pkg: 'com.android.calculator2', category: 'utility' },
  'com.google.android.apps.photos': { name: '相册', icon: 'photo_library', pkg: 'com.google.android.apps.photos', category: 'media' },
  'com.google.android.calendar': { name: '日历', icon: 'calendar_month', pkg: 'com.google.android.calendar', category: 'productivity' },
  'com.google.android.keep': { name: 'Keep 笔记', icon: 'note_alt', pkg: 'com.google.android.keep', category: 'productivity' },
  'com.android.vending': { name: '应用商店', icon: 'storefront', pkg: 'com.android.vending', category: 'tools' },
  'com.google.android.apps.messaging': { name: '短信', icon: 'chat', pkg: 'com.google.android.apps.messaging', category: 'communication' },

  // Popular Ecosystem Apps
  'com.tencent.mm': { name: '微信', icon: 'forum', pkg: 'com.tencent.mm', category: 'social' },
  'com.xingin.xhs': { name: '小红书', icon: 'auto_stories', pkg: 'com.xingin.xhs', category: 'social' },
  'com.sankuai.meituan': { name: '美团', icon: 'restaurant', pkg: 'com.sankuai.meituan', category: 'lifestyle' },
  'com.dianping.v1': { name: '大众点评', icon: 'star', pkg: 'com.dianping.v1', category: 'lifestyle' },
  'tv.danmaku.bili': { name: '哔哩哔哩', icon: 'video_library', pkg: 'tv.danmaku.bili', category: 'entertainment' },
  'com.eg.android.AlipayGphone': { name: '支付宝', icon: 'account_balance_wallet', pkg: 'com.eg.android.AlipayGphone', category: 'finance' },
  'com.netease.cloudmusic': { name: '网易云音乐', icon: 'headphones', pkg: 'com.netease.cloudmusic', category: 'entertainment' },
  'com.spotify.music': { name: 'Spotify', icon: 'music_note', pkg: 'com.spotify.music', category: 'entertainment' }
};

/**
 * Curated, clean task preset library (1~2 representative tasks per common app)
 */
export const SMART_TASK_LIBRARY: SmartSuggestion[] = [
  // 1. Google Maps
  {
    id: 'maps_coffee',
    title: '寻找附近精品咖啡店',
    description: '在谷歌地图中搜索附近评分最高的咖啡馆',
    goal: '打开谷歌地图，搜索附近评分最高的精品咖啡店，并查看排名第一的结果详情。',
    profile: 'flash',
    category: 'flash',
    tag: '谷歌地图',
    apps: [{ name: '谷歌地图', icon: 'explore', pkg: 'com.google.android.apps.maps' }],
    requiredPackages: ['com.google.android.apps.maps'],
    priority: 95
  },
  {
    id: 'pro_commute_share',
    title: '通勤耗时查询 + 短信草稿',
    description: '在地图查询通勤耗时，并在短信中起草到达时间',
    goal: '打开谷歌地图查询前往国际机场的通勤时间，计算到达时刻，然后打开短信应用起草一条告知到达时间的短信。',
    profile: 'pro',
    category: 'cross_app',
    tag: '谷歌地图 + 短信',
    apps: [
      { name: '谷歌地图', icon: 'explore', pkg: 'com.google.android.apps.maps' },
      { name: '短信', icon: 'chat', pkg: 'com.google.android.apps.messaging' }
    ],
    requiredPackages: ['com.google.android.apps.maps', 'com.google.android.apps.messaging'],
    matchMode: 'all',
    priority: 92
  },

  // 2. Gmail
  {
    id: 'gmail_receipts',
    title: '搜索订单与票据邮件',
    description: '在 Gmail 中查找最近的航班或快递确认邮件',
    goal: '打开 Gmail，搜索最近的航班行程或快递签收确认邮件。',
    profile: 'flash',
    category: 'flash',
    tag: 'Gmail',
    apps: [{ name: 'Gmail', icon: 'mail', pkg: 'com.google.android.gm' }],
    requiredPackages: ['com.google.android.gm'],
    priority: 90
  },
  {
    id: 'pro_email_to_calendar',
    title: '邮件行程同步到日历',
    description: '从 Gmail 提取航班或活动时间，并在日历中创建日程',
    goal: '打开 Gmail 找到最新的活动邀请或行程单，提取时间与地点，然后打开日历并创建对应的日程事件。',
    profile: 'pro',
    category: 'cross_app',
    tag: 'Gmail + 日历',
    apps: [
      { name: 'Gmail', icon: 'mail', pkg: 'com.google.android.gm' },
      { name: '日历', icon: 'calendar_month', pkg: 'com.google.android.calendar' }
    ],
    requiredPackages: ['com.google.android.gm'],
    priority: 94
  },

  // 3. Chrome
  {
    id: 'chrome_research',
    title: '搜索 AI 前沿进展',
    description: '在 Chrome 浏览器中搜索多模态 AI 最新进展',
    goal: '打开 Chrome 浏览器，搜索多模态移动端 AI 智能体的最新技术突破。',
    profile: 'flash',
    category: 'flash',
    tag: 'Chrome',
    apps: [{ name: 'Chrome 浏览器', icon: 'public', pkg: 'com.android.chrome' }],
    requiredPackages: ['com.android.chrome'],
    priority: 88
  },
  {
    id: 'pro_research_keep',
    title: '商品调研并记录笔记',
    description: '在 Chrome 对比前三款耳机，并在 Keep 中记录对比结论',
    goal: '打开 Chrome，调研前三款降噪耳机并对比价格与续航，然后在 Keep 笔记中撰写一份结构化的对比总结笔记。',
    profile: 'pro',
    category: 'pro',
    tag: 'Chrome + Keep 笔记',
    apps: [
      { name: 'Chrome 浏览器', icon: 'public', pkg: 'com.android.chrome' },
      { name: 'Keep 笔记', icon: 'note_alt', pkg: 'com.google.android.keep' }
    ],
    requiredPackages: ['com.android.chrome'],
    priority: 91
  },

  // 4. YouTube
  {
    id: 'youtube_lofi',
    title: '播放 Lo-Fi 音乐电台',
    description: '在 YouTube 搜索并播放 Lo-Fi 嘻哈直播电台',
    goal: '打开 YouTube，搜索 "Lofi hip hop beats relaxing radio"，并点击进入该直播。',
    profile: 'flash',
    category: 'flash',
    tag: 'YouTube',
    apps: [{ name: 'YouTube', icon: 'smart_display', pkg: 'com.google.android.youtube' }],
    requiredPackages: ['com.google.android.youtube'],
    priority: 85
  },

  // 5. Settings
  {
    id: 'settings_display_wifi',
    title: '深色模式与 Wi-Fi 检查',
    description: '在系统设置中切换深色主题并检查网络连接状态',
    goal: '打开系统设置，进入显示设置，确认深色主题已开启，并检查 Wi-Fi 连接状态。',
    profile: 'flash',
    category: 'flash',
    tag: 'Settings',
    apps: [{ name: '系统设置', icon: 'settings', pkg: 'com.android.settings' }],
    requiredPackages: ['com.android.settings'],
    priority: 87
  },
  {
    id: 'pro_settings_qa',
    title: '系统子模块健康度巡检',
    description: '遍历系统设置各子菜单，检查页面加载与崩溃弹窗',
    goal: '遍历系统设置的各个子菜单（网络、已连接设备、应用、电池、存储），确认每个页面均能正常加载且无无响应或崩溃弹窗，最后汇总巡检结果。',
    profile: 'pro',
    category: 'monitor',
    tag: '系统设置巡检',
    apps: [{ name: '系统设置', icon: 'settings', pkg: 'com.android.settings' }],
    requiredPackages: ['com.android.settings'],
    priority: 93
  },

  // 6. Clock
  {
    id: 'clock_timer',
    title: '25 分钟番茄钟计时',
    description: '在时钟应用中启动 25 分钟专注倒计时',
    goal: '打开时钟应用，切换到计时器标签页，设置 25 分钟并启动倒计时。',
    profile: 'flash',
    category: 'flash',
    tag: 'Clock',
    apps: [{ name: '时钟', icon: 'timer', pkg: 'com.google.android.deskclock' }],
    requiredPackages: ['com.google.android.deskclock', 'com.android.deskclock'],
    priority: 86
  },

  // 7. Calculator
  {
    id: 'calc_gratuity',
    title: '账单分摊与小费计算',
    description: '在计算器中对 186.40 元账单计算 18% 小费并按 3 人分摊',
    goal: '打开计算器，对 186.40 元的账单计算 18% 小费，再除以 3 人均摊。',
    profile: 'flash',
    category: 'flash',
    tag: 'Calculator',
    apps: [{ name: '计算器', icon: 'calculate', pkg: 'com.google.android.calculator' }],
    requiredPackages: ['com.google.android.calculator', 'com.android.calculator2'],
    priority: 84
  },

  // 8. Photos
  {
    id: 'photos_inspect',
    title: '查看最近一张截图',
    description: '打开相册并查看最新拍摄的屏幕截图',
    goal: '打开相册应用，在截图相簿中查看最新的一张截图。',
    profile: 'flash',
    category: 'flash',
    tag: 'Photos',
    apps: [{ name: '相册', icon: 'photo_library', pkg: 'com.google.android.apps.photos' }],
    requiredPackages: ['com.google.android.apps.photos'],
    priority: 82
  },

  // 9. WeChat
  {
    id: 'wechat_browse',
    title: '查看微信消息',
    description: '打开微信并查看最近的聊天会话',
    goal: '打开微信，查看排在最前面的最近聊天消息。',
    profile: 'flash',
    category: 'flash',
    tag: '微信',
    apps: [{ name: '微信', icon: 'forum', pkg: 'com.tencent.mm' }],
    requiredPackages: ['com.tencent.mm'],
    priority: 89
  },
  {
    id: 'pro_wechat_to_calendar',
    title: '微信通知同步到日历',
    description: '从微信聊天中提取会议通知并添加到日历',
    goal: '打开微信，在最前面的聊天中找到最新的会议通知或活动消息，提取时间与主题，然后打开日历创建对应日程。',
    profile: 'pro',
    category: 'cross_app',
    tag: '微信 + 日历',
    apps: [
      { name: '微信', icon: 'forum', pkg: 'com.tencent.mm' },
      { name: '日历', icon: 'calendar_month', pkg: 'com.google.android.calendar' }
    ],
    requiredPackages: ['com.tencent.mm'],
    priority: 93
  },

  // 10. Xiaohongshu
  {
    id: 'xhs_coffee_guide',
    title: '小红书咖啡探店攻略',
    description: '在小红书搜索热门的精品咖啡探店笔记',
    goal: '打开小红书，搜索评分最高的精品咖啡店，并查看排名第一的笔记。',
    profile: 'flash',
    category: 'flash',
    tag: '小红书',
    apps: [{ name: '小红书', icon: 'auto_stories', pkg: 'com.xingin.xhs' }],
    requiredPackages: ['com.xingin.xhs'],
    priority: 87
  },

  // 11. Meituan / Dianping
  {
    id: 'meituan_ramen_search',
    title: '美团美食搜索',
    description: '在美团或大众点评搜索附近评分最高的拉面',
    goal: '打开美团或大众点评，搜索附近评分最高的拉面店，并查看排名第一的商家评分。',
    profile: 'flash',
    category: 'flash',
    tag: '美团',
    apps: [{ name: '美团', icon: 'restaurant', pkg: 'com.sankuai.meituan' }],
    requiredPackages: ['com.sankuai.meituan', 'com.dianping.v1'],
    priority: 86
  },

  // 12. Bilibili
  {
    id: 'bilibili_stream',
    title: '哔哩哔哩科技视频',
    description: '在哔哩哔哩搜索并播放 AI 智能体教程视频',
    goal: '打开哔哩哔哩，搜索 "AI Agent 架构"，并播放匹配度最高的视频。',
    profile: 'flash',
    category: 'flash',
    tag: 'Bilibili',
    apps: [{ name: '哔哩哔哩', icon: 'video_library', pkg: 'tv.danmaku.bili' }],
    requiredPackages: ['tv.danmaku.bili'],
    priority: 85
  },

  // 13. Play Store
  {
    id: 'pro_playstore_review',
    title: '应用商店口碑调研',
    description: '在应用商店对比热门任务管理应用及其评分',
    goal: '打开应用商店，搜索评分最高的任务管理类应用，对比前两款候选应用的评分与最新用户评价，并记录推荐结论。',
    profile: 'pro',
    category: 'pro',
    tag: '应用商店',
    apps: [{ name: '应用商店', icon: 'storefront', pkg: 'com.android.vending' }],
    requiredPackages: ['com.android.vending'],
    priority: 88
  }
];
