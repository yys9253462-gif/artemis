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

import { Component, ChangeDetectionStrategy, inject, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentService } from '../../services/agent.service';
import { Session } from '../../core/models/session.model';
import { MarkdownSegment, MarkdownLine, NoteMilestone, ParsedNote } from '../../core/models/markdown.model';
import { parseNote, parseNoteLines } from '../../utils/markdown-parser.util';

export type { MarkdownSegment, MarkdownLine, NoteMilestone, ParsedNote };

@Component({
  selector: 'app-chat-interface',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-interface.component.html',
  styleUrl: './chat-interface.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class ChatInterfaceComponent {
  public agentService = inject(AgentService);

  public taskInput: string = '';
  // Signals so async completion handlers refresh this OnPush view.
  public isSubmitting = signal<boolean>(false);
  public errorMessage = signal<string | null>(null);

  // Device-serial resolution can require a JSON.parse of device_info; memoize
  // it per session object so template re-evaluation stays cheap.
  private deviceSerialCache = new WeakMap<Session, string | null>();

  /**
   * Filtered computed list of active tasks (running or pending) sorted by status and submission order
   */
  public activeQueue = computed(() => {
    const list = this.agentService.sessions().filter((s) => {
      const status = this.getTaskStatus(s);
      return status === 'running' || status === 'paused' || status === 'pending';
    });
    return list.sort((a, b) => {
      const statusA = this.getTaskStatus(a);
      const statusB = this.getTaskStatus(b);
      const isRunA = statusA === 'running' || statusA === 'paused';
      const isRunB = statusB === 'running' || statusB === 'paused';
      if (isRunA && !isRunB) return -1;
      if (!isRunA && isRunB) return 1;
      return (a.start_time || 0) - (b.start_time || 0); // stable FIFO order
    });
  });

  /**
   * Filtered computed list of historical/completed tasks (completed, failed, or cancelled)
   */
  public historyTasks = computed(() => {
    return this.agentService.sessions().filter((s) => {
      const status = this.getTaskStatus(s);
      return status === 'completed' || status === 'failed' || status === 'cancelled';
    });
  });

  public isMouseDownOnScreen = false;
  private touchStartX = 0;
  private touchStartY = 0;
  private touchStartTime = 0;
  public phoneTextInput = '';

  public onScreenMouseDown(event: MouseEvent, target: HTMLElement): void {
    this.isMouseDownOnScreen = true;
    const rect = target.getBoundingClientRect();
    this.touchStartX = (event.clientX - rect.left) / rect.width;
    this.touchStartY = (event.clientY - rect.top) / rect.height;
    this.touchStartTime = Date.now();
  }

  public onScreenMouseUp(event: MouseEvent, target: HTMLElement): void {
    if (!this.isMouseDownOnScreen) return;
    this.isMouseDownOnScreen = false;
    const rect = target.getBoundingClientRect();
    const endX = (event.clientX - rect.left) / rect.width;
    const endY = (event.clientY - rect.top) / rect.height;
    const duration = Date.now() - this.touchStartTime;

    const dx = Math.abs(endX - this.touchStartX);
    const dy = Math.abs(endY - this.touchStartY);

    if (dx < 0.03 && dy < 0.03) {
      this.sendTouch('tap', {
        x: Math.round(this.touchStartX * 1000),
        y: Math.round(this.touchStartY * 1000)
      });
    } else {
      this.sendTouch('swipe', {
        x1: Math.round(this.touchStartX * 1000),
        y1: Math.round(this.touchStartY * 1000),
        x2: Math.round(endX * 1000),
        y2: Math.round(endY * 1000),
        duration: Math.max(200, duration)
      });
    }
  }

  public sendTouch(action: string, payload: any): void {
    fetch('/api/stream/touch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...payload })
    }).catch(err => console.error('Touch send error:', err));
  }

  public sendKey(keycode: string): void {
    this.sendTouch('keyevent', { keycode });
  }

  public sendSwipe(dir: 'up' | 'down'): void {
    if (dir === 'up') {
      this.sendTouch('swipe', { x1: 500, y1: 800, x2: 500, y2: 200, duration: 300 });
    } else {
      this.sendTouch('swipe', { x1: 500, y1: 200, x2: 500, y2: 800, duration: 300 });
    }
  }

  public sendText(): void {
    const text = this.phoneTextInput.trim();
    if (!text) return;
    this.sendTouch('text', { text });
    this.phoneTextInput = '';
  }

  public launchNativeScrcpy(): void {
    fetch('/api/stream/launch-scrcpy', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (!data.success) {
          alert('唤起 Scrcpy 窗口失败: ' + (data.error || '未知错误'));
        }
      })
      .catch(err => alert('网络异常: ' + err.message));
  }

  // ⏰ Scheduler State for Workspace
  public scheduledTasks = signal<any[]>([]);
  public isCreatingScheduledTask = signal<boolean>(false);
  public newSchedName = '';
  public newSchedGoal = '';
  public newSchedType = 'daily';
  public newSchedTime = '08:30';
  public newSchedProfile = 'flash';

  public loadScheduledTasks(): void {
    fetch('/api/scheduler/tasks')
      .then(res => res.json())
      .then(data => {
        this.scheduledTasks.set(data.tasks || []);
      })
      .catch(err => console.error('Load scheduled tasks error:', err));
  }

  public saveScheduledTask(): void {
    if (!this.newSchedGoal.trim()) return;
    fetch('/api/scheduler/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: this.newSchedName.trim() || '未命名自动化任务',
        goal: this.newSchedGoal.trim(),
        schedule_type: this.newSchedType,
        schedule_time: this.newSchedTime.trim(),
        profile: this.newSchedProfile,
      })
    })
      .then(res => res.json())
      .then(() => {
        this.isCreatingScheduledTask.set(false);
        this.newSchedName = '';
        this.newSchedGoal = '';
        this.loadScheduledTasks();
      })
      .catch(err => console.error('Save scheduled task error:', err));
  }

  public triggerScheduledTask(taskId: string): void {
    fetch(`/api/scheduler/tasks/${taskId}/trigger`, { method: 'POST' })
      .then(res => res.json())
      .then(() => {
        this.agentService.fetchStatus();
        this.loadScheduledTasks();
      })
      .catch(err => console.error('Trigger error:', err));
  }

  public toggleScheduledTask(taskId: string, enabled: boolean): void {
    fetch(`/api/scheduler/tasks/${taskId}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    })
      .then(() => this.loadScheduledTasks())
      .catch(err => console.error('Toggle error:', err));
  }

  public deleteScheduledTask(taskId: string): void {
    fetch(`/api/scheduler/tasks/${taskId}`, { method: 'DELETE' })
      .then(() => this.loadScheduledTasks())
      .catch(err => console.error('Delete error:', err));
  }

  /**
   * Submit a new task goal to the backend
   */
  public submitTask(): void {
    const goal = this.taskInput.trim();
    if (!goal) {
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    this.agentService.runTask(goal).subscribe({
      next: (res) => {
        this.taskInput = '';
        this.isSubmitting.set(false);
        // Fetch status to refresh sessions list and select new session
        this.agentService.fetchStatus();
      },
      error: (err) => {
        console.error('Failed to submit task:', err);
        this.isSubmitting.set(false);
        this.errorMessage.set(err.error?.detail || 'The runner is busy. Please wait for the current task to finish.');
        // Auto-dismiss error banner after 5 seconds
        setTimeout(() => {
          this.errorMessage.set(null);
        }, 5000);
      }
    });
  }

  /**
   * Stop an individual task session
   */
  public stopTask(sessionId: string, event: MouseEvent): void {
    event.stopPropagation();
    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.agentService.stopTask(sessionId, false);
    setTimeout(() => {
      this.isSubmitting.set(false);
    }, 400);
  }

  /**
   * Stop the currently running task and optionally clear the backend queue
   */
  public stopTasks(stopAll: boolean = false): void {
    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.agentService.stopTask(stopAll);
    setTimeout(() => {
      this.isSubmitting.set(false);
    }, 400);
  }

  /**
   * Clear all database data/history to start fresh
   */
  public clearHistory(): void {
    if (!confirm('Are you sure you want to clear all tasks and history? This cannot be undone.')) {
      return;
    }
    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.agentService.clearAllHistory().subscribe({
      next: () => {
        this.isSubmitting.set(false);
      },
      error: (err: any) => {
        console.error('Failed to clear history:', err);
        this.isSubmitting.set(false);
        this.errorMessage.set(err.error?.detail || 'Failed to clear history.');
      }
    });
  }

  /**
   * Delete an individual task / session
   */
  public deleteTask(sessionId: string, event: MouseEvent): void {
    event.stopPropagation();
    if (!confirm(`Are you sure you want to delete this task? This cannot be undone.`)) {
      return;
    }
    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.agentService.deleteSession(sessionId).subscribe({
      next: () => {
        this.isSubmitting.set(false);
      },
      error: (err: any) => {
        console.error(`Failed to delete task ${sessionId}:`, err);
        this.isSubmitting.set(false);
        this.errorMessage.set(err.error?.detail || 'Failed to delete task.');
      }
    });
  }

  /**
   * Determine the current task execution status
   */
  public getTaskStatus(session: Session): 'running' | 'paused' | 'completed' | 'pending' | 'failed' | 'cancelled' {
    if (session.status) {
      const s = session.status.toLowerCase();
      if (s === 'completed' || s === 'success' || s === 'failed' || s === 'cancelled') {
        return (s === 'success' ? 'completed' : s) as any;
      }
      if (s === 'running' || s === 'paused' || s === 'pending') {
        return s as any;
      }
    }
    if (session.session_id === this.agentService.runningSessionId() && (this.agentService.agentStatus() === 'running' || this.agentService.agentStatus() === 'paused')) {
      return this.agentService.agentStatus() as 'running' | 'paused';
    }
    return 'completed';
  }

  /**
   * Determine the device serial number for the session
   */
  public getDeviceSerial(session: Session): string | null {
    if (this.deviceSerialCache.has(session)) {
      return this.deviceSerialCache.get(session) ?? null;
    }
    let resolved: string | null = null;
    const serial = session.device_serial || session.device_id;
    if (serial && serial !== 'pending' && serial !== 'null' && serial !== 'undefined') {
      resolved = serial;
    } else if (session.device_info) {
      try {
        const info = typeof session.device_info === 'string' ? JSON.parse(session.device_info) : session.device_info;
        const s = info?.device_id || info?.device_serial;
        if (s && s !== 'pending' && s !== 'null' && s !== 'undefined') {
          resolved = s;
        }
      } catch {
        // ignore
      }
    }
    this.deviceSerialCache.set(session, resolved);
    return resolved;
  }

  /**
   * Select a session in the UI to monitor its steps
   */
  public selectTask(sessionId: string): void {
    this.agentService.selectSession(sessionId, true);
  }

  // Notes Computed Properties
  public currentNoteContent = computed(() => {
    const notes = this.agentService.currentNotes();
    const key = this.agentService.selectedNoteKey();
    return notes[key] || '';
  });

  public noteKeys = computed(() => {
    return Object.keys(this.agentService.currentNotes()).filter(key => key.toLowerCase().endsWith('.md'));
  });

  public parsedNote = computed<ParsedNote>(() => {
    return this.getParsedNote(this.currentNoteContent());
  });

  public getParsedNote(content: string): ParsedNote {
    return parseNote(content);
  }

  public getParsedNoteLines(content: string): MarkdownLine[] {
    return parseNoteLines(content);
  }

  public selectNote(key: string): void {
    this.agentService.selectedNoteKey.set(key);
  }

  public trackSession(index: number, session: Session): string {
    return session.session_id;
  }

  public trackNoteKey(index: number, key: string): string {
    return key;
  }

  public trackMilestone(index: number, milestone: NoteMilestone): number {
    return milestone.index;
  }

  public trackMarkdownLine(index: number, line: MarkdownLine): number {
    return index;
  }
}
