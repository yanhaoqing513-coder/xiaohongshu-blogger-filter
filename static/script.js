/**
 * 博主筛选工具箱 - 前端交互逻辑
 * 支持两种模式：AI筛选 和 数据采集
 */

// 全局状态
const DEFAULT_FILTER_PROMPT = `筛选目标：寻找财经类社交平台博主。

合适的账号应满足：
1. 主页截图或OCR文字中能看到明确财经相关线索，例如：股票、基金、ETF、A股、港股、美股、投资、理财、资产配置、宏观经济、财报、公司分析、行业研究、商业模式、消费/科技/医药/新能源等行业投资分析，或者分享自己的每日投资心得（理财APP截图）。
2. 内容不是偶尔提到“赚钱/副业/职场/经纪人”，而是持续围绕财经、投资、市场、公司或产业分析展开。
3. 作品/笔记标题、封面文字、账号简介、可见话题中至少有两类证据指向财经内容；如果只有一个模糊词，请保守判断为不合适。
4. 优先选择有观点、有分析、有数据或案例拆解的账号。

不合适的账号包括：
1. 主要内容是美妆、穿搭、母婴、旅行、美食、情感、娱乐、健身、家居、留学等非财经领域。
2. 只讲搞钱、副业、职场成长、个人IP、创业鸡汤、销售带货，非垂直财经领域账号。
3. 纯广告、课程售卖、成功学、玄学暴富、无法从截图确认财经属性的账号。

请返回：合适/不合适、判断理由；如果不合适，用6个字以内说明不合适原因；同时对合适的账号给出账号分析，概括账号定位、财经相关证据、篇均点赞数和不确定需人工判断的信息。`;

const state = {
    mode: 'screening',     // 'screening' 或 'collecting'
    platform: 'xhs',       // 'xhs' 或 'douyin'
    analysisMode: 'vision', // 'vision' 或 'ocr'
    uploadedFile: null,
    filePath: null,
    taskId: null,
    isRunning: false,
    isLoggedIn: false,
    isLoggingIn: false,
    pollInterval: null
};

// DOM元素
const elements = {
    connectionStatus: document.getElementById('connectionStatus'),
    tabScreening: document.getElementById('tabScreening'),
    tabCollecting: document.getElementById('tabCollecting'),
    uploadArea: document.getElementById('uploadArea'),
    fileInput: document.getElementById('fileInput'),
    uploadPlaceholder: document.getElementById('uploadPlaceholder'),
    uploadSuccess: document.getElementById('uploadSuccess'),
    fileName: document.getElementById('fileName'),
    linkCount: document.getElementById('linkCount'),
    reuploadBtn: document.getElementById('reuploadBtn'),
    filterCard: document.getElementById('filterCard'),
    collectInfoCard: document.getElementById('collectInfoCard'),
    platformOptions: document.querySelectorAll('input[name="platform"]'),
    analysisOptions: document.querySelectorAll('input[name="analysisMode"]'),
    filterPrompt: document.getElementById('filterPrompt'),
    saveFilterPromptBtn: document.getElementById('saveFilterPromptBtn'),
    filterSaveStatus: document.getElementById('filterSaveStatus'),
    promptSettingsBtn: document.getElementById('promptSettingsBtn'),
    promptModal: document.getElementById('promptModal'),
    closePromptModalBtn: document.getElementById('closePromptModalBtn'),
    cancelPromptBtn: document.getElementById('cancelPromptBtn'),
    savePromptBtn: document.getElementById('savePromptBtn'),
    visionPromptTemplate: document.getElementById('visionPromptTemplate'),
    textPromptTemplate: document.getElementById('textPromptTemplate'),
    promptSaveStatus: document.getElementById('promptSaveStatus'),
    startBtn: document.getElementById('startBtn'),
    startBtnIcon: document.getElementById('startBtnIcon'),
    startBtnText: document.getElementById('startBtnText'),
    resultTitle: document.getElementById('resultTitle'),
    resultStats: document.getElementById('resultStats'),
    statMatched: document.getElementById('statMatched'),
    statUnmatched: document.getElementById('statUnmatched'),
    statCollected: document.getElementById('statCollected'),
    matchedCount: document.getElementById('matchedCount'),
    unmatchedCount: document.getElementById('unmatchedCount'),
    collectedCount: document.getElementById('collectedCount'),
    progressContainer: document.getElementById('progressContainer'),
    progressText: document.getElementById('progressText'),
    progressPercent: document.getElementById('progressPercent'),
    progressFill: document.getElementById('progressFill'),
    currentStep: document.getElementById('currentStep'),
    currentLink: document.getElementById('currentLink'),
    emptyState: document.getElementById('emptyState'),
    emptyHint: document.getElementById('emptyHint'),
    resultTable: document.getElementById('resultTable'),
    resultTableBody: document.getElementById('resultTableBody'),
    collectTable: document.getElementById('collectTable'),
    collectTableBody: document.getElementById('collectTableBody'),
    downloadSection: document.getElementById('downloadSection'),
    downloadBtn: document.getElementById('downloadBtn'),
    loginModal: document.getElementById('loginModal'),
    loginModalMessage: document.getElementById('loginModalMessage'),
    continueAfterLoginBtn: document.getElementById('continueAfterLoginBtn'),
    loginArea: document.getElementById('loginArea'),
    openBrowserBtn: document.getElementById('openBrowserBtn'),
    openBrowserBtnText: document.getElementById('openBrowserBtnText'),
    confirmLoginBtn: document.getElementById('confirmLoginBtn'),
    confirmLoginBtnText: document.getElementById('confirmLoginBtnText'),
    loginHint: document.getElementById('loginHint')
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    if (!elements.filterPrompt.value.trim()) {
        elements.filterPrompt.value = DEFAULT_FILTER_PROMPT;
    }
    initEventListeners();
    checkConnection();
    loadDefaultFilterPrompt();
    updateStartButton();
});

// 绑定事件
function initEventListeners() {
    // 模式切换
    elements.tabScreening.addEventListener('click', () => switchMode('screening'));
    elements.tabCollecting.addEventListener('click', () => switchMode('collecting'));

    // 上传区域点击
    elements.uploadArea.addEventListener('click', () => {
        if (!state.uploadedFile) {
            elements.fileInput.click();
        }
    });

    // 文件选择
    elements.fileInput.addEventListener('change', handleFileSelect);

    // 拖拽上传
    elements.uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.uploadArea.classList.add('dragover');
    });

    elements.uploadArea.addEventListener('dragleave', () => {
        elements.uploadArea.classList.remove('dragover');
    });

    elements.uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });

    // 重新上传
    elements.reuploadBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        resetUpload();
    });

    // 筛选条件变化
    elements.filterPrompt.addEventListener('input', updateStartButton);
    elements.saveFilterPromptBtn.addEventListener('click', saveDefaultFilterPrompt);
    elements.platformOptions.forEach(option => {
        option.addEventListener('change', handlePlatformChange);
    });
    elements.analysisOptions.forEach(option => {
        option.addEventListener('change', handleAnalysisModeChange);
    });

    // AI提示词设置
    elements.promptSettingsBtn.addEventListener('click', openPromptModal);
    elements.closePromptModalBtn.addEventListener('click', closePromptModal);
    elements.cancelPromptBtn.addEventListener('click', closePromptModal);
    elements.savePromptBtn.addEventListener('click', savePromptTemplate);
    elements.promptModal.addEventListener('click', (e) => {
        if (e.target === elements.promptModal) {
            closePromptModal();
        }
    });

    // 登录按钮
    elements.openBrowserBtn.addEventListener('click', openBrowserForLogin);
    elements.confirmLoginBtn.addEventListener('click', confirmLogin);
    elements.continueAfterLoginBtn.addEventListener('click', confirmTaskLogin);

    // 开始按钮
    elements.startBtn.addEventListener('click', startTask);

    // 下载结果
    elements.downloadBtn.addEventListener('click', downloadResult);
}

function handleAnalysisModeChange(e) {
    state.analysisMode = e.target.value;
    document.querySelectorAll('input[name="analysisMode"]').forEach(input => {
        const option = input.closest('.analysis-option');
        if (option) {
            option.classList.toggle('active', input.value === state.analysisMode);
        }
    });
}

function handlePlatformChange(e) {
    state.platform = e.target.value;
    document.querySelectorAll('input[name="platform"]').forEach(input => {
        const option = input.closest('.analysis-option');
        if (option) {
            option.classList.toggle('active', input.value === state.platform);
        }
    });

    if (state.uploadedFile) {
        resetUpload();
    }
}

async function loadDefaultFilterPrompt() {
    try {
        const response = await fetch('/api/default-filter-prompt');
        const data = await response.json();
        if (data.success && data.default_filter_prompt) {
            elements.filterPrompt.value = data.default_filter_prompt;
            updateStartButton();
        }
    } catch (error) {
        console.warn('默认筛选条件加载失败:', error);
    }
}

async function saveDefaultFilterPrompt() {
    const value = elements.filterPrompt.value.trim();

    if (!value) {
        elements.filterSaveStatus.textContent = '筛选条件不能为空';
        elements.filterSaveStatus.className = 'filter-save-status error';
        return;
    }

    elements.saveFilterPromptBtn.disabled = true;
    elements.filterSaveStatus.textContent = '保存中...';
    elements.filterSaveStatus.className = 'filter-save-status';

    try {
        const response = await fetch('/api/default-filter-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ default_filter_prompt: value })
        });
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || '保存失败');
        }

        elements.filterSaveStatus.textContent = '已保存';
        elements.filterSaveStatus.className = 'filter-save-status success';
    } catch (error) {
        elements.filterSaveStatus.textContent = '保存失败: ' + error.message;
        elements.filterSaveStatus.className = 'filter-save-status error';
    } finally {
        elements.saveFilterPromptBtn.disabled = false;
        setTimeout(() => {
            if (elements.filterSaveStatus.classList.contains('success')) {
                elements.filterSaveStatus.textContent = '';
                elements.filterSaveStatus.className = 'filter-save-status';
            }
        }, 1800);
    }
}

// ========== AI提示词设置 ==========

async function openPromptModal() {
    elements.promptModal.style.display = 'flex';
    elements.promptSaveStatus.textContent = '正在加载...';
    elements.promptSaveStatus.className = 'prompt-save-status';
    elements.savePromptBtn.disabled = true;

    try {
        const response = await fetch('/api/prompt-template');
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || '加载失败');
        }

        elements.visionPromptTemplate.value = data.vision_system_prompt || '';
        elements.textPromptTemplate.value = data.text_system_prompt || '';
        elements.promptSaveStatus.textContent = '';
        elements.savePromptBtn.disabled = false;
    } catch (error) {
        elements.promptSaveStatus.textContent = '加载失败: ' + error.message;
        elements.promptSaveStatus.className = 'prompt-save-status error';
    }
}

function closePromptModal() {
    elements.promptModal.style.display = 'none';
}

async function savePromptTemplate() {
    const visionPrompt = elements.visionPromptTemplate.value.trim();
    const textPrompt = elements.textPromptTemplate.value.trim();

    if (!visionPrompt || !textPrompt) {
        elements.promptSaveStatus.textContent = '两个提示词都不能为空';
        elements.promptSaveStatus.className = 'prompt-save-status error';
        return;
    }

    elements.savePromptBtn.disabled = true;
    elements.promptSaveStatus.textContent = '正在保存...';
    elements.promptSaveStatus.className = 'prompt-save-status';

    try {
        const response = await fetch('/api/prompt-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                vision_system_prompt: visionPrompt,
                text_system_prompt: textPrompt
            })
        });
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || '保存失败');
        }

        elements.promptSaveStatus.textContent = '已保存，下一次筛选会使用新提示词';
        elements.promptSaveStatus.className = 'prompt-save-status success';
        setTimeout(closePromptModal, 800);
    } catch (error) {
        elements.promptSaveStatus.textContent = '保存失败: ' + error.message;
        elements.promptSaveStatus.className = 'prompt-save-status error';
    } finally {
        elements.savePromptBtn.disabled = false;
    }
}

// ========== 模式切换 ==========

function switchMode(mode) {
    if (state.isRunning) return; // 运行中不允许切换

    state.mode = mode;

    // 更新Tab样式
    document.querySelectorAll('.mode-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.mode === mode);
    });

    if (mode === 'screening') {
        // AI筛选模式
        elements.filterCard.style.display = 'block';
        elements.collectInfoCard.style.display = 'none';
        elements.loginArea.style.display = 'none';
        elements.startBtnIcon.textContent = '🚀';
        elements.startBtnText.textContent = '开始筛选';
        elements.resultTitle.textContent = '筛选结果';
        elements.emptyHint.textContent = '上传Excel并开始筛选后，结果将显示在这里';

        // 显示筛选统计，隐藏采集统计
        elements.statMatched.style.display = '';
        elements.statUnmatched.style.display = '';
        elements.statCollected.style.display = 'none';
    } else {
        // 数据采集模式
        elements.filterCard.style.display = 'none';
        elements.collectInfoCard.style.display = 'block';
        elements.loginArea.style.display = 'block';
        elements.startBtnIcon.textContent = '📊';
        elements.startBtnText.textContent = '开始采集';
        elements.resultTitle.textContent = '采集结果';
        elements.emptyHint.textContent = '上传Excel并开始采集后，结果将显示在这里';

        // 隐藏筛选统计，显示采集统计
        elements.statMatched.style.display = 'none';
        elements.statUnmatched.style.display = 'none';
        elements.statCollected.style.display = '';
    }

    // 重置结果区域
    resetResults();
    updateStartButton();
}

function resetResults() {
    elements.resultStats.style.display = 'none';
    elements.progressContainer.style.display = 'none';
    elements.emptyState.style.display = 'flex';
    elements.resultTable.style.display = 'none';
    elements.collectTable.style.display = 'none';
    elements.downloadSection.style.display = 'none';
    elements.resultTableBody.innerHTML = '';
    elements.collectTableBody.innerHTML = '';
    elements.matchedCount.textContent = '0';
    elements.unmatchedCount.textContent = '0';
    elements.collectedCount.textContent = '0';
}

// ========== AI连接检查 ==========

async function checkConnection() {
    try {
        const response = await fetch('/api/test-connection');
        const data = await response.json();

        const statusDot = elements.connectionStatus.querySelector('.status-dot');
        const statusText = elements.connectionStatus.querySelector('.status-text');

        if (data.success && data.model_available) {
            statusDot.className = 'status-dot connected';
            statusText.textContent = `已连接: ${data.current_model}`;
        } else if (data.success) {
            statusDot.className = 'status-dot error';
            statusText.textContent = `模型未找到: ${data.current_model}`;
        } else {
            statusDot.className = 'status-dot error';
            statusText.textContent = 'AI服务未连接';
        }
    } catch (error) {
        const statusDot = elements.connectionStatus.querySelector('.status-dot');
        const statusText = elements.connectionStatus.querySelector('.status-text');
        statusDot.className = 'status-dot error';
        statusText.textContent = 'AI服务未连接';
    }
}

// ========== 文件上传 ==========

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

async function handleFile(file) {
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
        alert('只支持 .xlsx 和 .xls 格式的文件');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('platform', getActivePlatform());

    try {
        elements.uploadPlaceholder.innerHTML = `
            <div class="spinner" style="width:32px;height:32px;border-width:3px;"></div>
            <p>正在上传...</p>
        `;

        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            state.uploadedFile = file;
            state.filePath = data.file_path;

            elements.uploadPlaceholder.style.display = 'none';
            elements.uploadSuccess.style.display = 'flex';
            elements.fileName.textContent = data.original_filename;
            elements.linkCount.textContent = `检测到 ${data.link_count} 个${getPlatformLabel(getActivePlatform())}链接`;

            updateStartButton();
        } else {
            alert('上传失败: ' + data.error);
            resetUploadPlaceholder();
        }
    } catch (error) {
        alert('上传失败: ' + error.message);
        resetUploadPlaceholder();
    }
}

function resetUpload() {
    state.uploadedFile = null;
    state.filePath = null;
    elements.fileInput.value = '';
    elements.uploadPlaceholder.style.display = 'flex';
    elements.uploadSuccess.style.display = 'none';
    resetUploadPlaceholder();
    updateStartButton();
}

function resetUploadPlaceholder() {
    elements.uploadPlaceholder.innerHTML = `
        <span class="upload-icon">📊</span>
        <p>点击或拖拽Excel文件到这里</p>
        <span class="upload-hint">支持 .xlsx, .xls 格式</span>
    `;
}

// ========== 开始按钮 ==========

function updateStartButton() {
    const hasFile = state.uploadedFile !== null;

    if (state.mode === 'screening') {
        // AI筛选需要文件 + 筛选条件
        const hasPrompt = elements.filterPrompt.value.trim().length > 0;
        elements.startBtn.disabled = !(hasFile && hasPrompt) || state.isRunning;
    } else {
        // 数据采集需要文件 + 已登录
        elements.startBtn.disabled = !hasFile || !state.isLoggedIn || state.isRunning;
    }
}

// ========== 登录小红书 ==========

async function openBrowserForLogin() {
    elements.openBrowserBtnText.textContent = '正在打开浏览器...';
    elements.openBrowserBtn.disabled = true;

    try {
        const response = await fetch('/api/open-browser', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            elements.openBrowserBtnText.textContent = '✅ 浏览器已打开';
            elements.loginHint.textContent = '👉 请在弹出的浏览器中完成登录，登录完成后点下方「确认已登录」';
            elements.loginHint.style.color = '#fbbf24';
            // 显示确认按钮
            elements.confirmLoginBtn.style.display = 'flex';
            elements.confirmLoginBtn.disabled = false;
        } else {
            elements.openBrowserBtnText.textContent = '🔑 重新打开';
            elements.openBrowserBtn.disabled = false;
            elements.loginHint.textContent = '❌ 打开失败: ' + (data.error || '未知错误');
            elements.loginHint.style.color = '#f87171';
        }
    } catch (error) {
        elements.openBrowserBtnText.textContent = '🔑 重新打开';
        elements.openBrowserBtn.disabled = false;
        elements.loginHint.textContent = '❌ 出错: ' + error.message;
        elements.loginHint.style.color = '#f87171';
    }
}

function confirmLogin() {
    state.isLoggedIn = true;
    // 更新UI
    elements.openBrowserBtn.style.display = 'none';
    elements.confirmLoginBtn.style.display = 'none';
    elements.loginHint.textContent = '✅ 已确认登录，可以开始采集了！';
    elements.loginHint.style.color = '#4ade80';
    updateStartButton();
}

async function confirmTaskLogin() {
    if (!state.taskId) return;

    elements.continueAfterLoginBtn.disabled = true;
    elements.continueAfterLoginBtn.textContent = '正在继续...';

    try {
        const response = await fetch(`/api/confirm-login/${state.taskId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || '确认失败');
        }

        elements.loginModalMessage.textContent = '已确认登录，正在继续处理当前链接...';
    } catch (error) {
        alert('确认登录失败: ' + error.message);
        elements.continueAfterLoginBtn.disabled = false;
        elements.continueAfterLoginBtn.textContent = '我已登录，继续运行';
    }
}

// ========== 启动任务 ==========

async function startTask() {
    if (state.mode === 'screening') {
        await startScreening();
    } else {
        await startCollecting();
    }
}

async function startScreening() {
    if (!state.filePath || !elements.filterPrompt.value.trim()) {
        return;
    }

    state.isRunning = true;
    updateStartButton();
    prepareResultArea();

    // 显示筛选统计
    elements.statMatched.style.display = '';
    elements.statUnmatched.style.display = '';
    elements.statCollected.style.display = 'none';

    try {
        const response = await fetch('/api/start-screening', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: state.filePath,
                filter_prompt: elements.filterPrompt.value.trim(),
                analysis_mode: state.analysisMode,
                platform: getActivePlatform()
            })
        });

        const data = await response.json();

        if (data.success) {
            state.taskId = data.task_id;
            startPolling();
        } else {
            alert('启动筛选失败: ' + data.error);
            state.isRunning = false;
            updateStartButton();
        }
    } catch (error) {
        alert('启动筛选失败: ' + error.message);
        state.isRunning = false;
        updateStartButton();
    }
}

async function startCollecting() {
    if (!state.filePath) {
        return;
    }

    state.isRunning = true;
    updateStartButton();
    prepareResultArea();

    // 显示采集统计
    elements.statMatched.style.display = 'none';
    elements.statUnmatched.style.display = 'none';
    elements.statCollected.style.display = '';

    try {
        const response = await fetch('/api/start-collecting', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: state.filePath
            })
        });

        const data = await response.json();

        if (data.success) {
            state.taskId = data.task_id;
            startPolling();
        } else {
            alert('启动采集失败: ' + data.error);
            state.isRunning = false;
            updateStartButton();
        }
    } catch (error) {
        alert('启动采集失败: ' + error.message);
        state.isRunning = false;
        updateStartButton();
    }
}

function prepareResultArea() {
    elements.progressContainer.style.display = 'block';
    elements.emptyState.style.display = 'none';
    elements.resultStats.style.display = 'flex';
    elements.downloadSection.style.display = 'none';

    if (state.mode === 'screening') {
        elements.resultTable.style.display = 'table';
        elements.collectTable.style.display = 'none';
        elements.resultTableBody.innerHTML = '';
    } else {
        elements.resultTable.style.display = 'none';
        elements.collectTable.style.display = 'table';
        elements.collectTableBody.innerHTML = '';
    }
}

// ========== 轮询任务状态 ==========

function startPolling() {
    if (state.pollInterval) {
        clearInterval(state.pollInterval);
    }
    state.pollInterval = setInterval(pollTaskStatus, 2000);
    pollTaskStatus();
}

function stopPolling() {
    if (state.pollInterval) {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
    }
}

async function pollTaskStatus() {
    if (!state.taskId) return;

    try {
        const response = await fetch(`/api/task-status/${state.taskId}`);
        const data = await response.json();

        if (data.success) {
            updateProgress(data);

            if (state.mode === 'screening') {
                updateScreeningResults(data.results);
                elements.matchedCount.textContent = data.matched_count || 0;
                elements.unmatchedCount.textContent = data.unmatched_count || 0;
            } else {
                updateCollectingResults(data.results);
                const successCount = (data.results || []).filter(r => r.status === '成功').length;
                elements.collectedCount.textContent = successCount;
            }

            if (data.status === 'completed') {
                stopPolling();
                onTaskCompleted(data);
            } else if (data.status === 'error') {
                stopPolling();
                alert('任务出错: ' + data.error);
                state.isRunning = false;
                updateStartButton();
            } else if (data.status === 'need_login') {
                elements.loginModal.style.display = 'flex';
                elements.loginModalMessage.textContent = data.error || '请在弹出的浏览器窗口中完成登录或认证';
                elements.continueAfterLoginBtn.disabled = false;
                elements.continueAfterLoginBtn.textContent = '我已登录，继续运行';
            } else if (data.status === 'rate_limited') {
                elements.loginModal.style.display = 'none';
                elements.progressText.textContent = '访问过于频繁，暂停后自动重试';
                elements.currentLink.textContent = data.error || '已暂停3分钟';
            } else {
                elements.loginModal.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('轮询状态失败:', error);
    }
}

// ========== 进度更新 ==========

function updateProgress(data) {
    const progress = data.total > 0 ? (data.progress / data.total) * 100 : 0;
    const currentIndex = data.total > 0 ? Math.min(data.progress + 1, data.total) : 0;

    elements.progressFill.style.width = `${progress}%`;
    elements.progressPercent.textContent = `${Math.round(progress)}%`;
    elements.progressText.textContent = data.status === 'completed'
        ? `已完成 ${data.total}/${data.total}`
        : `正在处理 ${currentIndex}/${data.total}`;

    if (elements.currentStep) {
        elements.currentStep.textContent = `当前步骤：${data.current_step || '准备中'}`;
    }

    if (data.current_link) {
        elements.currentLink.textContent = `当前: ${data.current_link}`;
    } else {
        elements.currentLink.textContent = '';
    }
}

// ========== 结果表格 ==========

function updateScreeningResults(results) {
    if (!results || results.length === 0) return;

    elements.resultTableBody.innerHTML = '';

    results.forEach((result, index) => {
        const row = document.createElement('tr');
        row.className = 'fade-in';

        const matched = result.matched;
        const badgeClass = matched ? 'badge-success' : 'badge-secondary';
        const badgeText = matched ? '符合' : '不符合';

        row.innerHTML = `
            <td>${index + 1}</td>
            <td><a href="${result.link}" target="_blank" title="${result.link}">${truncateUrl(result.link)}</a></td>
            <td><span class="badge ${badgeClass}">${badgeText}</span></td>
            <td>${result.reason || result.content_summary || '-'}</td>
            <td>${result.account_analysis || result.content_summary || '-'}</td>
        `;

        elements.resultTableBody.appendChild(row);
    });
}

function updateCollectingResults(results) {
    if (!results || results.length === 0) return;

    elements.collectTableBody.innerHTML = '';

    results.forEach((result, index) => {
        const row = document.createElement('tr');
        row.className = 'fade-in';

        const isSuccess = result.status === '成功';
        const badgeClass = isSuccess ? 'badge-success' : (result.status === '被封禁' ? 'badge-danger' : 'badge-secondary');

        row.innerHTML = `
            <td>${index + 1}</td>
            <td><a href="${result.link}" target="_blank" title="${result.link}">${truncateUrl(result.link)}</a></td>
            <td>${result.fans || '-'}</td>
            <td><span class="badge ${badgeClass}">${result.status || '-'}</span></td>
        `;

        elements.collectTableBody.appendChild(row);
    });
}

function truncateUrl(url) {
    if (url.length > 40) {
        return url.substring(0, 40) + '...';
    }
    return url;
}

function getActivePlatform() {
    return state.mode === 'collecting' ? 'xhs' : state.platform;
}

function getPlatformLabel(platform = getActivePlatform()) {
    return platform === 'douyin' ? '抖音' : '小红书';
}

// ========== 任务完成 ==========

function onTaskCompleted(data) {
    state.isRunning = false;
    updateStartButton();

    const doneText = state.mode === 'screening' ? '筛选完成!' : '采集完成!';
    elements.progressText.textContent = doneText;
    elements.progressPercent.textContent = '100%';
    elements.progressFill.style.width = '100%';
    if (elements.currentStep) {
        elements.currentStep.textContent = '当前步骤：全部完成';
    }
    elements.currentLink.textContent = '';

    if (data.output_file) {
        elements.downloadSection.style.display = 'block';
        elements.downloadBtn.dataset.filename = data.output_file;
    }

    elements.loginModal.style.display = 'none';
}

// ========== 下载结果 ==========

function downloadResult() {
    const filename = elements.downloadBtn.dataset.filename;
    if (filename) {
        window.location.href = `/api/download/${filename}`;
    }
}
