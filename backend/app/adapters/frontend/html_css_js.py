"""HTML5 + CSS3 + Vanilla JavaScript frontend adapter."""

from __future__ import annotations

import json

from app.adapters.base import FrontendAdapter, ScaffoldContext, ScaffoldFile


class HTMLCssJsAdapter(FrontendAdapter):
    """Clean, dependency-free HTML5 + CSS3 + Vanilla JavaScript adapter."""

    key = "html_css_js"
    display_name = "HTML / CSS / JavaScript"
    language = "JavaScript"
    version = "ES2024"
    description = (
        "Modern semantic HTML5, responsive vanilla CSS, and clean JavaScript "
        "without node_modules or heavy build-tool overhead."
    )
    tags = ("html5", "css3", "vanilla-js", "lightweight", "no-build")
    best_for = (
        "Landing pages and portfolio sites",
        "Fast-loading web applications",
        "Zero-dependency lightweight deployments",
    )

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ctx.project_name}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>%E2%9C%93</text></svg>">
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <header class="header">
        <div class="container header-container">
            <div class="brand">
                <span class="logo-icon">&#10003;</span>
                <h1 class="logo">{ctx.project_name}</h1>
            </div>
            <nav class="nav">
                <a href="#app" class="nav-link">Tasks</a>
                <a href="#about" class="nav-link">About</a>
            </nav>
        </div>
    </header>

    <main class="main container">
        <section class="hero">
            <h2>Modern Task Manager</h2>
            <p>{ctx.description}</p>
        </section>

        <!-- Search and Filter Controls -->
        <section class="controls-section">
            <div class="search-box">
                <input type="search" id="search-input" placeholder="Search tasks..." aria-label="Search tasks">
            </div>
            <div class="filter-tabs" role="tablist">
                <button type="button" class="filter-btn active" data-filter="all" id="filter-all" role="tab" aria-selected="true">All</button>
                <button type="button" class="filter-btn" data-filter="active" id="filter-active" role="tab" aria-selected="false">Active</button>
                <button type="button" class="filter-btn" data-filter="completed" id="filter-completed" role="tab" aria-selected="false">Completed</button>
            </div>
            <div class="stats-counter" id="stats-display">
                <span class="stat-badge">Total: <strong id="stat-total">0</strong></span>
                <span class="stat-badge">Active: <strong id="stat-active">0</strong></span>
                <span class="stat-badge">Completed: <strong id="stat-completed">0</strong></span>
            </div>
        </section>

        <!-- Task Creation Form -->
        <section class="form-section">
            <form id="task-form" novalidate>
                <div class="form-group">
                    <label for="task-title" class="sr-only">Task Title</label>
                    <input type="text" id="task-title" placeholder="What needs to be done?" required aria-label="Task title">
                </div>
                <div class="form-group">
                    <label for="task-desc" class="sr-only">Task Description</label>
                    <textarea id="task-desc" placeholder="Details or notes (optional)" aria-label="Task description"></textarea>
                </div>
                <div class="form-row">
                    <div class="select-wrapper">
                        <label for="task-priority" class="sr-only">Priority</label>
                        <select id="task-priority" aria-label="Priority">
                            <option value="low">Low Priority</option>
                            <option value="medium" selected>Medium Priority</option>
                            <option value="high">High Priority</option>
                        </select>
                    </div>
                    <div class="date-wrapper">
                        <label for="task-due-date" class="sr-only">Due date</label>
                        <input type="date" id="task-due-date" aria-label="Due date">
                    </div>
                    <button type="submit" id="add-task-btn" class="btn btn-primary">Add Task</button>
                </div>
                <div id="validation-msg" class="validation-message hidden" role="alert"></div>
            </form>
        </section>

        <!-- Task List and Empty State -->
        <section id="app" class="app-section">
            <div id="task-list" class="task-list"></div>
            <div id="empty-state" class="empty-state">
                <div class="empty-icon">&#128221;</div>
                <h3>No tasks found</h3>
                <p>Create a new task to get started!</p>
            </div>
        </section>
    </main>

    <!-- Delete Confirmation Modal -->
    <div id="delete-modal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal-dialog">
            <h3 id="modal-title">Confirm Deletion</h3>
            <p>Are you sure you want to delete this task? This action cannot be undone.</p>
            <div class="modal-actions">
                <button type="button" id="cancel-delete-btn" class="btn btn-secondary">Cancel</button>
                <button type="button" id="confirm-delete-btn" class="btn btn-danger">Delete</button>
            </div>
        </div>
    </div>

    <!-- Edit Task Modal -->
    <div id="edit-modal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="edit-modal-title">
        <div class="modal-dialog">
            <h3 id="edit-modal-title">Edit Task</h3>
            <form id="edit-task-form" novalidate>
                <input type="hidden" id="edit-task-id">
                <div class="form-group">
                    <label for="edit-task-title" class="sr-only">Edit Task Title</label>
                    <input type="text" id="edit-task-title" placeholder="Task title" required aria-label="Edit task title">
                </div>
                <div class="form-group">
                    <label for="edit-task-desc" class="sr-only">Edit Description</label>
                    <textarea id="edit-task-desc" placeholder="Task details" aria-label="Edit description"></textarea>
                </div>
                <div class="form-row">
                    <div class="select-wrapper">
                        <label for="edit-task-priority" class="sr-only">Edit Priority</label>
                        <select id="edit-task-priority" aria-label="Edit priority">
                            <option value="low">Low Priority</option>
                            <option value="medium">Medium Priority</option>
                            <option value="high">High Priority</option>
                        </select>
                    </div>
                    <div class="date-wrapper">
                        <label for="edit-task-due-date" class="sr-only">Edit Due Date</label>
                        <input type="date" id="edit-task-due-date" aria-label="Edit due date">
                    </div>
                </div>
                <div id="edit-validation-msg" class="validation-message hidden" role="alert"></div>
                <div class="modal-actions">
                    <button type="button" id="cancel-edit-btn" class="btn btn-secondary">Cancel</button>
                    <button type="submit" id="save-edit-btn" class="btn btn-primary">Save Changes</button>
                </div>
            </form>
        </div>
    </div>

    <footer class="footer" id="about">
        <div class="container">
            <p>&copy; {ctx.project_name}. Modern, accessible task manager with localStorage persistence.</p>
        </div>
    </footer>

    <script type="module" src="js/app.js"></script>
</body>
</html>
"""

        styles_css = """/* Modern Design Tokens and Responsive Styles */
:root {
    --primary: #2563eb;
    --primary-hover: #1d4ed8;
    --danger: #dc2626;
    --danger-hover: #b91c1c;
    --secondary: #64748b;
    --secondary-hover: #475569;
    --background: #f8fafc;
    --surface: #ffffff;
    --text: #0f172a;
    --text-muted: #64748b;
    --border: #e2e8f0;
    --radius: 8px;
    --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
    --font: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: var(--font);
    background-color: var(--background);
    color: var(--text);
    line-height: 1.6;
    overflow-x: hidden;
}

.container {
    max-width: 1000px;
    margin: 0 auto;
    padding: 0 1.5rem;
}

.header {
    background-color: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 1rem 0;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}

.header-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.logo-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: var(--primary);
    color: #fff;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: bold;
}

.logo {
    font-size: 1.35rem;
    font-weight: 700;
    color: var(--text);
}

.nav a {
    color: var(--text-muted);
    text-decoration: none;
    margin-left: 1.5rem;
    font-weight: 500;
    transition: color 0.2s;
}

.nav a:hover, .nav a:focus-visible {
    color: var(--primary);
}

.hero {
    text-align: center;
    padding: 2rem 0 1.25rem;
}

.hero h2 {
    font-size: 2rem;
    margin-bottom: 0.35rem;
    color: var(--text);
}

.hero p {
    color: var(--text-muted);
    max-width: 600px;
    margin: 0 auto;
}

.controls-section {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
    justify-content: space-between;
    background: var(--surface);
    padding: 1rem 1.25rem;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    margin-bottom: 1.5rem;
    box-shadow: var(--shadow);
}

.search-box input {
    padding: 0.55rem 0.85rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    min-width: 240px;
    font-size: 0.95rem;
}

.search-box input:focus {
    outline: 2px solid var(--primary);
    border-color: transparent;
}

.filter-tabs {
    display: flex;
    gap: 0.5rem;
}

.filter-btn {
    padding: 0.45rem 1rem;
    border: 1px solid var(--border);
    background: var(--background);
    color: var(--text);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 500;
    transition: all 0.2s;
}

.filter-btn:hover {
    background: #e2e8f0;
}

.filter-btn.active {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}

.stats-counter {
    display: flex;
    gap: 0.75rem;
    font-size: 0.9rem;
    color: var(--text-muted);
}

.stat-badge {
    background: var(--background);
    padding: 0.35rem 0.65rem;
    border-radius: 6px;
    border: 1px solid var(--border);
}

.stat-badge strong {
    color: var(--text);
}

.form-section {
    background: var(--surface);
    padding: 1.5rem;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    margin-bottom: 1.5rem;
    box-shadow: var(--shadow);
}

.form-group {
    margin-bottom: 0.75rem;
}

.form-group input, .form-group textarea, .form-row select, .form-row input {
    width: 100%;
    padding: 0.65rem 0.85rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-family: inherit;
    font-size: 0.95rem;
}

.form-group input:focus, .form-group textarea:focus, .form-row select:focus, .form-row input:focus {
    outline: 2px solid var(--primary);
    border-color: transparent;
}

.form-group textarea {
    min-height: 70px;
    resize: vertical;
}

.form-row {
    display: flex;
    gap: 0.75rem;
    align-items: center;
}

.select-wrapper, .date-wrapper {
    flex: 1;
}

.btn {
    padding: 0.65rem 1.25rem;
    border: none;
    border-radius: var(--radius);
    cursor: pointer;
    font-weight: 600;
    font-size: 0.95rem;
    transition: background 0.2s, transform 0.1s;
    white-space: nowrap;
}

.btn:active {
    transform: scale(0.98);
}

.btn-primary {
    background: var(--primary);
    color: #fff;
}

.btn-primary:hover {
    background: var(--primary-hover);
}

.btn-secondary {
    background: var(--secondary);
    color: #fff;
}

.btn-secondary:hover {
    background: var(--secondary-hover);
}

.btn-danger {
    background: var(--danger);
    color: #fff;
}

.btn-danger:hover {
    background: var(--danger-hover);
}

.validation-message {
    margin-top: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: #fef2f2;
    color: var(--danger);
    border: 1px solid #fecaca;
    border-radius: var(--radius);
    font-size: 0.875rem;
    font-weight: 500;
}

.task-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.task-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    transition: transform 0.15s, box-shadow 0.15s;
}

.task-card:hover {
    box-shadow: var(--shadow);
}

.task-card.completed {
    opacity: 0.65;
    background: #f8fafc;
}

.task-card.completed .task-title {
    text-decoration: line-through;
    color: var(--text-muted);
}

.task-main {
    display: flex;
    align-items: flex-start;
    gap: 0.85rem;
    flex: 1;
}

.task-checkbox {
    margin-top: 0.25rem;
    width: 18px;
    height: 18px;
    cursor: pointer;
    accent-color: var(--primary);
}

.task-content {
    flex: 1;
}

.task-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 0.2rem;
}

.task-description {
    font-size: 0.9rem;
    color: var(--text-muted);
    margin-bottom: 0.4rem;
}

.task-meta {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.8rem;
}

.priority-badge {
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-weight: 600;
    text-transform: capitalize;
}

.priority-low {
    background: #e0f2fe;
    color: #0369a1;
}

.priority-medium {
    background: #fef3c7;
    color: #b45309;
}

.priority-high {
    background: #fee2e2;
    color: #b91c1c;
}

.due-date {
    color: var(--text-muted);
}

.task-actions {
    display: flex;
    gap: 0.5rem;
}

.btn-icon {
    padding: 0.4rem 0.75rem;
    font-size: 0.85rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    cursor: pointer;
    font-weight: 500;
    transition: background 0.15s;
}

.btn-icon:hover {
    background: #f1f5f9;
}

.empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--text-muted);
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: var(--radius);
}

.empty-icon {
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
}

.hidden {
    display: none !important;
}

.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
}

.modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(2px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.modal-dialog {
    background: var(--surface);
    padding: 2rem;
    border-radius: var(--radius);
    max-width: 480px;
    width: 90%;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2);
}

.modal-dialog h3 {
    margin-bottom: 0.75rem;
    font-size: 1.25rem;
}

.modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    margin-top: 1.5rem;
}

.footer {
    border-top: 1px solid var(--border);
    padding: 2rem 0;
    text-align: center;
    color: var(--text-muted);
    font-size: 0.9rem;
    margin-top: 3rem;
}

@media (max-width: 768px) {
    .controls-section {
        flex-direction: column;
        align-items: stretch;
    }
    .search-box input {
        min-width: 100%;
    }
    .form-row {
        flex-direction: column;
        align-items: stretch;
    }
    .task-card {
        flex-direction: column;
        align-items: stretch;
    }
    .task-actions {
        justify-content: flex-end;
    }
}
"""

        storage_js = """// Storage persistence manager for tasks
export const STORAGE_KEY = 'aegis_tasks_data';

export function loadTasks() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        console.warn('Storage corrupted or unavailable, recovering with empty state.');
        return [];
    }
}

export function saveTasks(tasks) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
        return true;
    } catch (err) {
        console.error('Failed to save tasks to localStorage:', err);
        return false;
    }
}

export function clearTasks() {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // Safe no-op
    }
}
"""

        app_js = """import { loadTasks, saveTasks } from './storage.js';

let tasks = [];
let currentFilter = 'all';
let searchQuery = '';
let taskToDeleteId = null;

export function updateMetrics(taskList = tasks) {
    const total = taskList.length;
    const completed = taskList.filter(t => t.completed).length;
    const active = total - completed;

    const tEl = document.getElementById('stat-total');
    const aEl = document.getElementById('stat-active');
    const cEl = document.getElementById('stat-completed');

    if (tEl) tEl.textContent = total;
    if (aEl) aEl.textContent = active;
    if (cEl) cEl.textContent = completed;
}

export function renderTasks() {
    const listContainer = document.getElementById('task-list');
    const emptyState = document.getElementById('empty-state');
    if (!listContainer) return;

    let filtered = tasks;

    // Apply active/completed filter
    if (currentFilter === 'active') {
        filtered = filtered.filter(t => !t.completed);
    } else if (currentFilter === 'completed') {
        filtered = filtered.filter(t => t.completed);
    }

    // Apply search filter
    if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        filtered = filtered.filter(t =>
            (t.title && t.title.toLowerCase().includes(q)) ||
            (t.description && t.description.toLowerCase().includes(q))
        );
    }

    listContainer.innerHTML = '';

    if (filtered.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
    } else {
        if (emptyState) emptyState.classList.add('hidden');

        filtered.forEach(task => {
            const card = document.createElement('div');
            card.className = `task-card ${task.completed ? 'completed' : ''}`;
            card.dataset.id = task.id;

            const priorityClass = `priority-${task.priority || 'medium'}`;

            card.innerHTML = `
                <div class="task-main">
                    <input type="checkbox" class="task-checkbox" ${task.completed ? 'checked' : ''} aria-label="Mark task complete">
                    <div class="task-content">
                        <div class="task-title">${escapeHtml(task.title)}</div>
                        ${task.description ? `<div class="task-description">${escapeHtml(task.description)}</div>` : ''}
                        <div class="task-meta">
                            <span class="priority-badge ${priorityClass}">${escapeHtml(task.priority || 'medium')}</span>
                            ${task.dueDate ? `<span class="due-date">Due: ${escapeHtml(task.dueDate)}</span>` : ''}
                        </div>
                    </div>
                </div>
                <div class="task-actions">
                    <button type="button" class="btn-icon edit-btn" data-id="${task.id}" aria-label="Edit task">Edit</button>
                    <button type="button" class="btn-icon delete-btn" data-id="${task.id}" aria-label="Delete task">Delete</button>
                </div>
            `;

            // Toggle completed checkbox
            const checkbox = card.querySelector('.task-checkbox');
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    toggleTask(task.id);
                });
            }

            // Edit button
            const editBtn = card.querySelector('.edit-btn');
            if (editBtn) {
                editBtn.addEventListener('click', () => {
                    openEditModal(task.id);
                });
            }

            // Delete button
            const delBtn = card.querySelector('.delete-btn');
            if (delBtn) {
                delBtn.addEventListener('click', () => {
                    openDeleteModal(task.id);
                });
            }

            listContainer.appendChild(card);
        });
    }

    updateMetrics(tasks);
}

export function createTask(taskData) {
    const newTask = {
        id: Date.now().toString(),
        title: taskData.title.trim(),
        description: (taskData.description || '').trim(),
        priority: taskData.priority || 'medium',
        dueDate: taskData.dueDate || '',
        completed: false,
        createdAt: new Date().toISOString(),
    };
    tasks = [newTask, ...tasks];
    saveTasks(tasks);
    renderTasks();
    return newTask;
}

export function editTask(id, updatedData) {
    tasks = tasks.map(t => {
        if (t.id === id) {
            return {
                ...t,
                title: updatedData.title.trim(),
                description: (updatedData.description || '').trim(),
                priority: updatedData.priority || t.priority,
                dueDate: updatedData.dueDate !== undefined ? updatedData.dueDate : t.dueDate,
            };
        }
        return t;
    });
    saveTasks(tasks);
    renderTasks();
}

export function toggleTask(id) {
    tasks = tasks.map(t => t.id === id ? { ...t, completed: !t.completed } : t);
    saveTasks(tasks);
    renderTasks();
}

export function deleteTask(id) {
    tasks = tasks.filter(t => t.id !== id);
    saveTasks(tasks);
    renderTasks();
}

export function openDeleteModal(id) {
    taskToDeleteId = id;
    const modal = document.getElementById('delete-modal');
    if (modal) modal.classList.remove('hidden');
}

export function closeDeleteModal() {
    taskToDeleteId = null;
    const modal = document.getElementById('delete-modal');
    if (modal) modal.classList.add('hidden');
}

export function openEditModal(id) {
    const task = tasks.find(t => t.id === id);
    if (!task) return;

    const modal = document.getElementById('edit-modal');
    const idInput = document.getElementById('edit-task-id');
    const titleInput = document.getElementById('edit-task-title');
    const descInput = document.getElementById('edit-task-desc');
    const priorityInput = document.getElementById('edit-task-priority');
    const dueDateInput = document.getElementById('edit-task-due-date');
    const valMsg = document.getElementById('edit-validation-msg');

    if (idInput) idInput.value = task.id;
    if (titleInput) titleInput.value = task.title;
    if (descInput) descInput.value = task.description || '';
    if (priorityInput) priorityInput.value = task.priority || 'medium';
    if (dueDateInput) dueDateInput.value = task.dueDate || '';
    if (valMsg) {
        valMsg.textContent = '';
        valMsg.classList.add('hidden');
    }

    if (modal) modal.classList.remove('hidden');
}

export function closeEditModal() {
    const modal = document.getElementById('edit-modal');
    if (modal) modal.classList.add('hidden');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    tasks = loadTasks();

    // Form submission
    const taskForm = document.getElementById('task-form');
    const valMsg = document.getElementById('validation-msg');
    if (taskForm) {
        taskForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const titleInput = document.getElementById('task-title');
            const descInput = document.getElementById('task-desc');
            const priorityInput = document.getElementById('task-priority');
            const dueDateInput = document.getElementById('task-due-date');

            const title = titleInput ? titleInput.value.trim() : '';

            if (!title) {
                if (valMsg) {
                    valMsg.textContent = 'Task title is required.';
                    valMsg.classList.remove('hidden');
                }
                return;
            }

            if (valMsg) {
                valMsg.textContent = '';
                valMsg.classList.add('hidden');
            }

            createTask({
                title,
                description: descInput ? descInput.value : '',
                priority: priorityInput ? priorityInput.value : 'medium',
                dueDate: dueDateInput ? dueDateInput.value : '',
            });

            taskForm.reset();
            if (priorityInput) priorityInput.value = 'medium';
        });
    }

    // Edit form submission
    const editForm = document.getElementById('edit-task-form');
    const editValMsg = document.getElementById('edit-validation-msg');
    if (editForm) {
        editForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const idInput = document.getElementById('edit-task-id');
            const titleInput = document.getElementById('edit-task-title');
            const descInput = document.getElementById('edit-task-desc');
            const priorityInput = document.getElementById('edit-task-priority');
            const dueDateInput = document.getElementById('edit-task-due-date');

            const id = idInput ? idInput.value : '';
            const title = titleInput ? titleInput.value.trim() : '';

            if (!title) {
                if (editValMsg) {
                    editValMsg.textContent = 'Task title cannot be empty.';
                    editValMsg.classList.remove('hidden');
                }
                return;
            }

            editTask(id, {
                title,
                description: descInput ? descInput.value : '',
                priority: priorityInput ? priorityInput.value : 'medium',
                dueDate: dueDateInput ? dueDateInput.value : '',
            });

            closeEditModal();
        });
    }

    // Cancel edit
    const cancelEditBtn = document.getElementById('cancel-edit-btn');
    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', closeEditModal);
    }

    // Delete modal confirmation
    const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', () => {
            if (taskToDeleteId) {
                deleteTask(taskToDeleteId);
            }
            closeDeleteModal();
        });
    }

    // Cancel delete
    const cancelDeleteBtn = document.getElementById('cancel-delete-btn');
    if (cancelDeleteBtn) {
        cancelDeleteBtn.addEventListener('click', closeDeleteModal);
    }

    // Search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value;
            renderTasks();
        });
    }

    // Filter buttons
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            currentFilter = btn.dataset.filter || 'all';
            renderTasks();
        });
    });

    renderTasks();
});
"""

        package_json = {
            "name": f"{ctx.project_slug}-web",
            "version": "1.0.0",
            "type": "module",
            "description": ctx.description[:180],
            "scripts": {
                "dev": f"npx serve -l {ctx.web_port}",
                "start": f"npx serve -l {ctx.web_port}",
            },
        }

        readme_md = f"""# {ctx.project_name}

Modern Task Manager Web App built with HTML5, CSS3, and Vanilla JavaScript.

## Features
- **Create, Edit, Delete Tasks**: Full task lifecycle with confirmation modal.
- **Completion States**: Mark completed, toggle back to active.
- **Filters & Search**: Real-time search by keywords and filter tabs (All, Active, Completed).
- **Priorities & Due Dates**: Low, Medium, High priorities with colored badges and date indicators.
- **Metrics Dashboard**: Real-time counts for Total, Active, and Completed tasks.
- **Validation**: User-friendly form validation messages.
- **localStorage Persistence**: Automatically saves and restores tasks across browser reloads, with safe corrupted-data recovery.
- **Responsive Design**: Mobile-first layout with smooth desktop and tablet breakpoints.

## Running Locally
To run locally, you can serve the directory using any static file server:
```bash
python -m http.server 8000
```
Or with Node.js:
```bash
npx serve -l 8000
```
"""

        return [
            ScaffoldFile(
                path="frontend/index.html",
                content=index_html,
                description="HTML5 root document",
            ),
            ScaffoldFile(
                path="frontend/css/styles.css",
                content=styles_css,
                description="Global stylesheet",
            ),
            ScaffoldFile(
                path="frontend/js/storage.js",
                content=storage_js,
                description="Local storage persistence helper",
            ),
            ScaffoldFile(
                path="frontend/js/app.js",
                content=app_js,
                description="JavaScript application entrypoint",
            ),
            ScaffoldFile(
                path="frontend/package.json",
                content=json.dumps(package_json, indent=2),
                description="Minimal dev server package definition",
            ),
            ScaffoldFile(
                path="frontend/README.md",
                content=readme_md,
                description="Project documentation and run instructions",
            ),
        ]

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        return f"""# syntax=docker/dockerfile:1

FROM nginx:1.27-alpine AS runtime
COPY . /usr/share/nginx/html
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
    CMD wget -q --spider http://localhost/ || exit 1

USER nginx
CMD ["nginx", "-g", "daemon off;"]
"""

    def compose_service(self, ctx: ScaffoldContext) -> dict:
        return {
            "build": {"context": "./frontend"},
            "ports": [f"{ctx.web_port}:80"],
            "depends_on": ["api"] if ctx.needs_backend else [],
        }

    def conventions(self, ctx: ScaffoldContext) -> str:
        return (
            "Frontend Conventions:\n"
            "- HTML files must be clean semantic HTML5 with responsive layout.\n"
            "- CSS files use CSS custom properties (variables) defined in :root.\n"
            "- JavaScript files use modern ES modules (import/export).\n"
            "- Implement complete, working functionality in frontend/index.html, frontend/css/styles.css, "
            "and frontend/js/app.js (plus optional modular helpers under frontend/js/).\n"
        )

