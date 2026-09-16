/**
 * Image studio page.
 *
 * Readers of this deployment do not share one language, so no sentence is written
 * directly into the DOM. Every string goes through t(), which reads the locale the
 * host bridge reports and re-renders when the reader switches language. Failures
 * coming back from the plugin's HTTP endpoints are stable snake_case codes, looked
 * up in the same dictionary.
 */
(async function () {
  "use strict";
  const bridge = window.CapstonePluginPage;
  const $ = (id) => document.getElementById(id);

  const STRINGS = {
    zh: {
      "app.title": "图像工作室",
      "app.tagline": "从一个想法，到下一版作品。",
      "nav.label": "工作室导航",
      "tab.create": "创作",
      "tab.templates": "提示词模板",
      "tab.history": "我的任务",
      "tab.analytics": "使用统计",
      "action.refresh": "刷新",
      "action.testConnection": "检查模型配置",
      "action.generate": "生成图像",
      "action.submitEdit": "提交改图",
      "action.previous": "上一页",
      "action.next": "下一页",
      "action.useTemplate": "使用模板",
      "action.continueFrom": "以此图继续修改",
      "action.reuse": "复用提示词与参数",
      "action.retry": "载入参数重试",
      "create.heading": "开始创作",
      "create.subheading": "自由描述，或从提示词模板开始。",
      "create.editHeading": "基于参考图创作",
      "create.continueHeading": "继续修改这版作品",
      "field.prompt": "提示词",
      "field.promptPlaceholder":
        "描述主体、场景、构图和风格。改图时说明需要保留和修改的部分。",
      "field.size": "画幅",
      "field.count": "数量",
      "size.square": "正方形 · 1024 × 1024",
      "size.landscape": "横向 · 1536 × 1024",
      "size.portrait": "纵向 · 1024 × 1536",
      "reference.title": "参考图",
      "reference.hint": "上传图片，或从作品中选择。PNG / JPEG / WebP，最大 8 MiB。",
      "reference.choose": "选择参考图",
      "reference.current": "当前参考图",
      "reference.clear": "移除参考图",
      "reference.uploading": "正在上传参考图…",
      "reference.ready": "参考图已就绪",
      "reference.historic": "历史参考图",
      "reference.gone": "原参考图已不可用，请重新选择后提交。",
      "gallery.heading": "我的作品",
      "gallery.hint": "选择作品继续改图",
      "gallery.empty": "还没有作品，从左侧开始生成第一张图片。",
      "gallery.updated": "作品列表已更新，可选择作品继续修改。",
      "gallery.imageAlt": "生成作品",
      "gallery.imageGone": "图片已被清理或暂时不可用",
      "templates.heading": "提示词模板",
      "templates.hint": "应用模板后替换花括号中的变量，提示词可自由调整。",
      "templates.category": "模板分类",
      "templates.allCategories": "全部分类",
      "templates.needsReference": "需要参考图",
      "templates.variables": "替换变量：",
      "templates.current": "当前模板：",
      "templates.pickReference": "请先选择参考图",
      "templates.reused": "复用历史任务参数",
      "templates.attribution":
        "分类与工作流参考 EvoLinkAI / awesome-gpt-image-2-API-and-Prompts；本站模板为原创参数化改写。",
      "history.heading": "我的任务",
      "history.search": "搜索提示词",
      "history.statusLabel": "任务状态",
      "history.empty": "没有符合条件的任务。",
      "history.details": "任务详情",
      "history.taskId": "任务 ID：",
      "history.parent": "来源任务：",
      "history.noParent": "无",
      "history.duration": "耗时：",
      "history.seconds": " 秒",
      "history.images": " 张",
      "history.cacheHit": "缓存命中",
      "history.fileCleaned": "文件已被清理",
      "history.page": "第 {page} / {pages} 页 · 共 {total} 个任务",
      "mode.generate": "文生图",
      "mode.edit": "图像编辑",
      "status.all": "全部状态",
      "status.queued": "执行中",
      "status.running": "工具执行中",
      "status.success": "已完成",
      "status.error": "失败",
      "status.interrupted": "已中断",
      "analytics.heading": "使用统计",
      "analytics.hint": "模块汇总 · 按 UTC 自然日统计 · 活跃用户为提交过任务的去重用户",
      "analytics.range": "统计周期",
      "analytics.days7": "最近 7 天",
      "analytics.days30": "最近 30 天",
      "analytics.days90": "最近 90 天",
      "analytics.chartTitle": "每日使用次数",
      "analytics.chartHint": "一次生成或编辑提交计一次使用，包含失败和缓存命中。",
      "analytics.chartAlt": "每日使用次数折线图，详细数值见下方明细表",
      "analytics.tableToggle": "查看每日明细",
      "analytics.totalTasks": "历史任务总数",
      "analytics.uses": "周期内使用次数",
      "analytics.activeUsers": "周期内活跃用户",
      "analytics.success": "成功任务",
      "analytics.failed": "失败 / 中断",
      "analytics.cacheHits": "缓存命中",
      "analytics.outputImages": "新产出图片",
      "analytics.edits": "改图任务",
      "analytics.date": "日期 (UTC)",
      "analytics.usesShort": "使用次数",
      "analytics.activeUsersShort": "活跃用户",
      "analytics.successShort": "成功",
      "analytics.failedShort": "失败 / 中断",
      "analytics.point": "{date}：{uses} 次",
      "notice.submitted": "任务已提交，生成完成后作品会自动刷新。",
      "notice.submittedDetail": "任务已提交：{id}。可在“我的任务”查看进度，也可以继续创作。",
      "notice.replaceVariables": "请先替换提示词中花括号标记的变量。",
      "notice.templateNeedsReference": "此模板需要先选择参考图。",
      "notice.loadFailed": "加载失败：{message}",
      "notice.uploadFailed": "上传失败：{message}",
      "notice.submitFailed": "提交失败：{message}",
      "notice.initFailed": "工作室初始化失败：{message}",
      "notice.connectionOk": "模型配置可用：{provider} / {model}。为保护密钥，未主动向外部地址发请求。",
      "notice.fileTooLarge": "参考图不能超过 8 MiB",
      "notice.unreadableFile": "无法读取图片",
      "error.reference_required": "请先选择一张参考图。",
      "error.reference_too_large": "参考图不能超过 8 MiB。",
      "error.reference_unsupported_format": "仅支持 PNG / JPEG / WebP，最多 2000 万像素。",
      "error.reference_invalid": "这张图片无法解析，请换一张。",
      "error.reference_missing": "参考图不存在或已被清理。",
      "error.reference_not_in_parent": "这张参考图不属于所选的来源任务。",
      "error.template_requires_reference": "此模板需要参考图。",
      "error.unknown_template": "模板不存在。",
      "error.prompt_required": "请填写提示词。",
      "error.prompt_too_long": "提示词过长，最多 12000 个字符。",
      "error.invalid_size_or_count": "画幅或数量不合法，数量需在 1 到 4 之间。",
      "error.invalid_request": "请求格式不正确。",
      "error.invalid_days": "统计周期只能是 7、30 或 90 天。",
      "error.invalid_limit": "数量参数不合法。",
      "error.invalid_page": "页码不合法。",
      "error.unknown_task": "任务不存在。",
      "error.unknown_image": "图片不存在。",
      "error.image_unavailable": "图片已被清理或暂时不可用。",
      "error.too_many_pending_tasks": "最多同时提交 3 个任务，请等待当前任务完成。",
      "error.executor_unavailable": "图像生成服务暂不可用。",
      "error.storage_unavailable": "存储服务暂不可用，请稍后重试。",
      "error.host_model_unconfigured": "宿主模型未配置完整，请先在模型设置中配置服务商、模型和密钥。",
      "error.custom_model_unconfigured": "插件专用服务未配置完整，请填写 API 地址和密钥。",
      "error.invalid_model_source": "模型来源配置无效。",
      "error.task_failed": "任务失败或执行中断，请检查服务配置后重试。",
      "error.missing_prompt": "请填写提示词。",
      "error.missing_source_image": "请先选择要修改的图片。",
      "error.source_image_unavailable": "要修改的图片已不可用，请重新选择。",
      "error.mask_unavailable": "蒙版图片已不可用，请重新选择。",
      "error.missing_api_key": "图像服务密钥未配置，请在插件详情页填写。",
      "error.provider_edit_unsupported": "当前图像服务不支持以图生图，请在插件设置中改用支持改图的服务或模型。",
      "error.provider_unauthorized": "图像服务拒绝了本次请求，请检查密钥是否有效。",
      "error.provider_rate_limited": "图像服务请求过于频繁，请稍后重试。",
      "error.provider_rejected": "图像服务拒绝了本次请求，请调整提示词或参数后重试。",
      "error.provider_timeout": "图像服务响应超时，请稍后重试。",
      "error.provider_unreachable": "无法连接图像服务，请检查网络与服务地址。",
      "error.provider_failed": "图像服务调用失败，请稍后重试。",
    },
    en: {
      "app.title": "Image Studio",
      "app.tagline": "From an idea to the next version of it.",
      "nav.label": "Studio sections",
      "tab.create": "Create",
      "tab.templates": "Templates",
      "tab.history": "My tasks",
      "tab.analytics": "Usage",
      "action.refresh": "Refresh",
      "action.testConnection": "Check model config",
      "action.generate": "Generate image",
      "action.submitEdit": "Submit edit",
      "action.previous": "Previous",
      "action.next": "Next",
      "action.useTemplate": "Use template",
      "action.continueFrom": "Edit this image",
      "action.reuse": "Reuse prompt and settings",
      "action.retry": "Load settings and retry",
      "create.heading": "Start creating",
      "create.subheading": "Describe what you want, or start from a template.",
      "create.editHeading": "Create from a reference image",
      "create.continueHeading": "Keep editing this version",
      "field.prompt": "Prompt",
      "field.promptPlaceholder":
        "Describe the subject, setting, composition and style. When editing, say what to keep and what to change.",
      "field.size": "Aspect",
      "field.count": "Count",
      "size.square": "Square · 1024 × 1024",
      "size.landscape": "Landscape · 1536 × 1024",
      "size.portrait": "Portrait · 1024 × 1536",
      "reference.title": "Reference image",
      "reference.hint": "Upload an image or pick one of your results. PNG / JPEG / WebP, up to 8 MiB.",
      "reference.choose": "Choose a reference image",
      "reference.current": "Current reference image",
      "reference.clear": "Remove reference",
      "reference.uploading": "Uploading the reference image…",
      "reference.ready": "Reference image ready",
      "reference.historic": "Earlier reference image",
      "reference.gone": "That reference image is gone. Pick another one before submitting.",
      "gallery.heading": "My images",
      "gallery.hint": "Pick an image to keep editing",
      "gallery.empty": "Nothing here yet. Generate your first image on the left.",
      "gallery.updated": "New images are available. Pick one to keep editing.",
      "gallery.imageAlt": "Generated image",
      "gallery.imageGone": "This image was cleaned up or is temporarily unavailable",
      "templates.heading": "Prompt templates",
      "templates.hint": "Apply a template, replace the values in braces, then edit the prompt freely.",
      "templates.category": "Template category",
      "templates.allCategories": "All categories",
      "templates.needsReference": "needs a reference image",
      "templates.variables": "Replace: ",
      "templates.current": "Template: ",
      "templates.pickReference": "pick a reference image first",
      "templates.reused": "Settings reused from an earlier task",
      "templates.attribution":
        "Categories and workflow informed by EvoLinkAI / awesome-gpt-image-2-API-and-Prompts. The templates here are original parameterised rewrites.",
      "history.heading": "My tasks",
      "history.search": "Search prompts",
      "history.statusLabel": "Task status",
      "history.empty": "No task matches these filters.",
      "history.details": "Task details",
      "history.taskId": "Task ID: ",
      "history.parent": "Source task: ",
      "history.noParent": "none",
      "history.duration": "Took: ",
      "history.seconds": " s",
      "history.images": " image(s)",
      "history.cacheHit": "cache hit",
      "history.fileCleaned": "file was cleaned up",
      "history.page": "Page {page} of {pages} · {total} task(s)",
      "mode.generate": "Text to image",
      "mode.edit": "Image edit",
      "status.all": "All statuses",
      "status.queued": "Running",
      "status.running": "Tool running",
      "status.success": "Done",
      "status.error": "Failed",
      "status.interrupted": "Interrupted",
      "analytics.heading": "Usage",
      "analytics.hint":
        "Module totals · bucketed by UTC calendar day · active users are distinct submitters",
      "analytics.range": "Reporting period",
      "analytics.days7": "Last 7 days",
      "analytics.days30": "Last 30 days",
      "analytics.days90": "Last 90 days",
      "analytics.chartTitle": "Daily usage",
      "analytics.chartHint":
        "Each generate or edit submission counts once, including failures and cache hits.",
      "analytics.chartAlt": "Line chart of daily usage; exact values are in the table below",
      "analytics.tableToggle": "Show daily breakdown",
      "analytics.totalTasks": "Tasks all time",
      "analytics.uses": "Uses in period",
      "analytics.activeUsers": "Active users in period",
      "analytics.success": "Successful tasks",
      "analytics.failed": "Failed / interrupted",
      "analytics.cacheHits": "Cache hits",
      "analytics.outputImages": "New images produced",
      "analytics.edits": "Edit tasks",
      "analytics.date": "Date (UTC)",
      "analytics.usesShort": "Uses",
      "analytics.activeUsersShort": "Active users",
      "analytics.successShort": "Succeeded",
      "analytics.failedShort": "Failed / interrupted",
      "analytics.point": "{date}: {uses} use(s)",
      "notice.submitted": "Task submitted. Your images refresh automatically when it finishes.",
      "notice.submittedDetail":
        "Task submitted: {id}. Track it under My tasks, or keep creating here.",
      "notice.replaceVariables": "Replace the values in braces before submitting.",
      "notice.templateNeedsReference": "This template needs a reference image first.",
      "notice.loadFailed": "Could not load: {message}",
      "notice.uploadFailed": "Upload failed: {message}",
      "notice.submitFailed": "Submission failed: {message}",
      "notice.initFailed": "The studio could not start: {message}",
      "notice.connectionOk": "Model configuration is ready: {provider} / {model}. No external request was made to protect the key.",
      "notice.fileTooLarge": "A reference image must be 8 MiB or smaller",
      "notice.unreadableFile": "Could not read that image",
      "error.reference_required": "Choose a reference image first.",
      "error.reference_too_large": "A reference image must be 8 MiB or smaller.",
      "error.reference_unsupported_format": "Only PNG, JPEG and WebP up to 20 megapixels are supported.",
      "error.reference_invalid": "That image could not be read. Try another one.",
      "error.reference_missing": "That reference image no longer exists.",
      "error.reference_not_in_parent": "That reference image does not belong to the chosen source task.",
      "error.template_requires_reference": "This template needs a reference image.",
      "error.unknown_template": "That template does not exist.",
      "error.prompt_required": "Write a prompt first.",
      "error.prompt_too_long": "The prompt is too long; 12000 characters maximum.",
      "error.invalid_size_or_count": "Invalid aspect or count; the count must be between 1 and 4.",
      "error.invalid_request": "The request was malformed.",
      "error.invalid_days": "The reporting period must be 7, 30 or 90 days.",
      "error.invalid_limit": "That limit is not valid.",
      "error.invalid_page": "That page number is not valid.",
      "error.unknown_task": "That task does not exist.",
      "error.unknown_image": "That image does not exist.",
      "error.image_unavailable": "That image was cleaned up or is temporarily unavailable.",
      "error.too_many_pending_tasks": "Three tasks can run at once. Wait for one to finish.",
      "error.executor_unavailable": "Image generation is unavailable right now.",
      "error.storage_unavailable": "Storage is unavailable right now. Try again shortly.",
      "error.host_model_unconfigured": "The host model is incomplete. Configure its provider, model and key first.",
      "error.custom_model_unconfigured": "The plugin-specific service is incomplete. Enter its API URL and key.",
      "error.invalid_model_source": "The model source setting is invalid.",
      "error.task_failed": "The task failed or was interrupted. Check the service settings and retry.",
      "error.missing_prompt": "Write a prompt first.",
      "error.missing_source_image": "Choose the image you want to edit.",
      "error.source_image_unavailable": "The image you wanted to edit is no longer available. Pick another one.",
      "error.mask_unavailable": "The mask image is no longer available. Pick another one.",
      "error.missing_api_key": "No image service key is configured. Enter it on the plugin details page.",
      "error.provider_edit_unsupported": "This image service cannot edit images. Switch to a service or model that supports it in the plugin settings.",
      "error.provider_unauthorized": "The image service refused the request. Check that the key is valid.",
      "error.provider_rate_limited": "The image service is rate limiting requests. Try again shortly.",
      "error.provider_rejected": "The image service refused the request. Adjust the prompt or settings and retry.",
      "error.provider_timeout": "The image service timed out. Try again shortly.",
      "error.provider_unreachable": "The image service could not be reached. Check the network and the service address.",
      "error.provider_failed": "The image service call failed. Try again shortly.",
    },
  };

  let locale = "en";

  /** Look up a key for the current locale, filling {placeholders} from vars. */
  function t(key, vars) {
    const table = STRINGS[locale] || STRINGS.en;
    const value = table[key] !== undefined ? table[key] : (STRINGS.en[key] ?? key);
    if (!vars) return value;
    return value.replace(/\{(\w+)\}/g, (whole, name) =>
      vars[name] === undefined ? whole : String(vars[name]),
    );
  }

  /** A manifest value is either a plain string or a {zh, en} map written by the plugin. */
  function localized(value) {
    if (value && typeof value === "object")
      return value[locale] !== undefined ? value[locale] : (value.en ?? Object.values(value)[0] ?? "");
    return value === undefined || value === null ? "" : String(value);
  }

  /**
   * Turn whatever the bridge threw into readable text. The endpoints answer with a
   * message code; anything else is a transport failure and is shown verbatim.
   */
  function reason(error) {
    const raw = error && error.message ? String(error.message) : String(error || "");
    const table = STRINGS[locale] || STRINGS.en;
    return table["error." + raw] !== undefined ? table["error." + raw] : (STRINGS.en["error." + raw] ?? raw);
  }

  function applyStaticText() {
    document.documentElement.setAttribute("lang", locale === "zh" ? "zh-CN" : "en");
    document.title = t("app.title");
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
    });
    document.querySelectorAll("[data-i18n-alt]").forEach((el) => {
      el.setAttribute("alt", t(el.dataset.i18nAlt));
    });
  }

  let templates = [],
    reference = null,
    parentId = null,
    templateId = null,
    page = 1,
    total = 0;
  let gallerySignature = "",
    historySignature = "",
    historyRequest = 0;
  let refreshing = false,
    uploadBusy = false,
    currentTab = "create",
    searchTimer;
  const element = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  function notice(text) {
    $("notice").textContent = text;
  }
  function tab(name) {
    currentTab = name;
    document.querySelectorAll(".panel").forEach((el) => {
      el.hidden = el.id !== name;
    });
    document
      .querySelectorAll("[data-tab]")
      .forEach((el) => el.setAttribute("aria-selected", String(el.dataset.tab === name)));
    if (name === "history") void loadHistory().catch((error) => notice(reason(error)));
    if (name === "analytics") void loadStats().catch((error) => notice(reason(error)));
  }
  function button(label, action) {
    const el = element("button", label);
    el.type = "button";
    el.addEventListener("click", () =>
      Promise.resolve()
        .then(action)
        .catch((error) => notice(reason(error))),
    );
    return el;
  }
  async function selectReference(asset, taskId) {
    const url = await bridge.dataUrl("thumbnail", { id: asset.id });
    reference = asset;
    parentId = taskId || null;
    $("reference-image").src = url;
    $("reference-name").textContent = asset.name;
    $("reference-preview").hidden = false;
    $("generate-button").textContent = t("action.submitEdit");
    $("mode-title").textContent = t(taskId ? "create.continueHeading" : "create.editHeading");
    tab("create");
  }
  function clearReference() {
    reference = null;
    parentId = null;
    $("reference-preview").hidden = true;
    $("reference-image").removeAttribute("src");
    $("upload").value = "";
    $("generate-button").textContent = t("action.generate");
    $("mode-title").textContent = t("create.heading");
  }
  const observer = new IntersectionObserver(
    (entries) =>
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        bridge
          .dataUrl("thumbnail", { id: entry.target.dataset.asset })
          .then((url) => {
            entry.target.src = url;
          })
          .catch(() => {
            entry.target.alt = t("gallery.imageGone");
          });
      }),
    { rootMargin: "150px" },
  );
  function card(asset, taskId) {
    const el = element("article", undefined, "card");
    const img = element("img");
    img.alt = t("gallery.imageAlt");
    img.dataset.asset = asset.id;
    observer.observe(img);
    el.append(img);
    const caption = element("div", undefined, "caption");
    caption.append(element("small", asset.name));
    caption.append(
      button(t("action.continueFrom"), async () => {
        await selectReference(asset, taskId);
        $("prompt").focus();
      }),
    );
    el.append(caption);
    return el;
  }
  async function loadGallery() {
    const data = await bridge.apiGet("gallery", { limit: 60 });
    const signature = JSON.stringify(data.items);
    if (signature === gallerySignature) return;
    if (gallerySignature && data.items.length) notice(t("gallery.updated"));
    gallerySignature = signature;
    $("grid")
      .querySelectorAll("img")
      .forEach((img) => observer.unobserve(img));
    $("grid").replaceChildren(...data.items.map((asset) => card(asset, asset.task_id)));
    $("empty").hidden = data.items.length > 0;
  }
  function renderTemplates() {
    $("template-grid").replaceChildren();
    templates
      .filter((item) => !$("category").value || localized(item.category) === $("category").value)
      .forEach((item) => {
        const el = element("article", undefined, "template-card");
        el.append(
          element(
            "small",
            localized(item.category) +
              (item.requires_reference ? " · " + t("templates.needsReference") : ""),
            "eyebrow",
          ),
          element("h3", localized(item.title)),
          element("p", localized(item.prompt)),
          element("small", t("templates.variables") + localized(item.variables), "muted"),
        );
        el.append(
          button(t("action.useTemplate"), () => {
            templateId = item.id;
            $("prompt").value = localized(item.prompt);
            $("template-label").textContent =
              t("templates.current") +
              localized(item.title) +
              (item.requires_reference ? " · " + t("templates.pickReference") : "");
            tab("create");
            $("prompt").focus();
          }),
        );
        $("template-grid").append(el);
      });
  }
  function renderCategories() {
    const selected = $("category").value;
    const options = [...new Set(templates.map((item) => localized(item.category)))];
    $("category").replaceChildren(
      Object.assign(element("option", t("templates.allCategories")), { value: "" }),
      ...options.map((name) => Object.assign(element("option", name), { value: name })),
    );
    $("category").value = options.includes(selected) ? selected : "";
  }
  async function reuse(task) {
    $("prompt").value = task.prompt;
    $("size").value = task.size;
    $("image-count").value = task.image_count;
    templateId = task.template_id || null;
    $("template-label").textContent = t("templates.reused");
    clearReference();
    if (task.reference) {
      try {
        await selectReference({ id: task.reference, name: t("reference.historic") }, task.parent_id);
      } catch (_) {
        notice(t("reference.gone"));
      }
    }
    tab("create");
  }
  async function loadHistory() {
    const requestId = ++historyRequest;
    const data = await bridge.apiGet("history", {
      page,
      status: $("status-filter").value,
      search: $("search").value,
    });
    if (requestId !== historyRequest) return;
    const signature = JSON.stringify(data);
    if (signature === historySignature) return;
    historySignature = signature;
    total = data.total;
    $("history-list")
      .querySelectorAll("img")
      .forEach((img) => observer.unobserve(img));
    $("history-list").replaceChildren();
    if (!data.items.length) $("history-list").append(element("p", t("history.empty"), "empty"));
    data.items.forEach((task) => {
      const el = element("article", undefined, "task");
      const header = element("div", undefined, "section-heading");
      header.append(
        element(
          "strong",
          t(task.mode === "edit" ? "mode.edit" : "mode.generate") +
            " · " +
            t("status." + task.status, undefined),
        ),
        element("time", new Date(task.created * 1000).toLocaleString(locale)),
      );
      el.append(header, element("p", task.prompt, "task-prompt"));
      el.append(
        element(
          "small",
          task.size +
            " · " +
            task.image_count +
            t("history.images") +
            (task.model ? " · " + task.model : "") +
            (task.source === "cache" ? " · " + t("history.cacheHit") : ""),
          "muted",
        ),
      );
      const details = element("details");
      details.append(element("summary", t("history.details")));
      details.append(
        element("p", t("history.taskId") + task.id),
        element("p", t("history.parent") + (task.parent_id || t("history.noParent"))),
      );
      if (task.finished)
        details.append(
          element(
            "p",
            t("history.duration") +
              Math.max(0, task.finished - task.created).toFixed(1) +
              t("history.seconds"),
          ),
        );
      el.append(details);
      // The backend stores a message code, never a sentence.
      if (task.error) el.append(element("p", reason(task.error), "error"));
      const outputs = element("div", undefined, "grid task-images");
      task.images.forEach((asset) =>
        outputs.append(
          asset.available
            ? card(asset, task.id)
            : element("p", asset.name + " · " + t("history.fileCleaned"), "muted"),
        ),
      );
      el.append(
        outputs,
        button(
          t(task.status === "error" || task.status === "interrupted" ? "action.retry" : "action.reuse"),
          () => reuse(task),
        ),
      );
      $("history-list").append(el);
    });
    $("previous").disabled = page <= 1;
    $("next").disabled = page * 20 >= total;
    $("page-label").textContent = t("history.page", {
      page,
      pages: Math.max(1, Math.ceil(total / 20)),
      total,
    });
  }
  async function loadStats() {
    const data = await bridge.apiGet("stats", { days: $("days").value });
    const rows = [
      ["analytics.totalTasks", data.total_tasks],
      ["analytics.uses", data.uses],
      ["analytics.activeUsers", data.active_users],
      ["analytics.success", data.success],
      ["analytics.failed", data.failed],
      ["analytics.cacheHits", data.cache_hits],
      ["analytics.outputImages", data.output_images],
      ["analytics.edits", data.edits],
    ];
    $("stats").replaceChildren(
      ...rows.map(([key, value]) => {
        const el = element("div", undefined, "stat");
        el.append(element("span", t(key)), element("strong", String(value)));
        return el;
      }),
    );
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 900 240");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", t("analytics.chartAlt"));
    const max = Math.max(1, ...data.series.map((r) => r.uses));
    const points = data.series.map((r, i) => [
      50 + (i * 820) / Math.max(1, data.series.length - 1),
      195 - (r.uses / max) * 165,
    ]);
    function svgEl(tag, attrs, text) {
      const el = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
      if (text !== undefined) el.textContent = text;
      svg.append(el);
      return el;
    }
    for (let i = 0; i <= 3; i++) {
      const y = 195 - i * 55;
      svgEl("line", { x1: 50, x2: 870, y1: y, y2: y, stroke: "var(--border)" });
      svgEl(
        "text",
        { x: 38, y: y + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 12 },
        String(Math.round((max * i) / 3)),
      );
    }
    svgEl("polyline", {
      points: points.map((p) => p.join(",")).join(" "),
      fill: "none",
      stroke: "var(--accent)",
      "stroke-width": 3,
    });
    points.forEach(([x, y], i) => {
      const dot = svgEl("circle", { cx: x, cy: y, r: 3, fill: "var(--accent)" });
      const title = document.createElementNS(ns, "title");
      title.textContent = t("analytics.point", {
        date: data.series[i].date,
        uses: data.series[i].uses,
      });
      dot.append(title);
    });
    svgEl("text", { x: 50, y: 224, fill: "var(--muted)", "font-size": 12 }, data.series[0].date);
    svgEl(
      "text",
      { x: 870, y: 224, fill: "var(--muted)", "text-anchor": "end", "font-size": 12 },
      data.series[data.series.length - 1].date,
    );
    $("chart").replaceChildren(svg);
    const table = element("table"),
      head = element("tr");
    [
      "analytics.date",
      "analytics.usesShort",
      "analytics.activeUsersShort",
      "analytics.successShort",
      "analytics.failedShort",
    ].forEach((key) => head.append(element("th", t(key))));
    const thead = element("thead");
    thead.append(head);
    table.append(thead);
    const tbody = element("tbody");
    data.series.forEach((row) => {
      const tr = element("tr");
      [row.date, row.uses, row.active_users, row.success, row.failed].forEach((v) =>
        tr.append(element("td", String(v))),
      );
      tbody.append(tr);
    });
    table.append(tbody);
    $("daily-table").replaceChildren(table);
  }
  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      await loadGallery();
      if (currentTab === "history") await loadHistory();
      if (currentTab === "analytics") await loadStats();
    } catch (error) {
      notice(t("notice.loadFailed", { message: reason(error) }));
    } finally {
      refreshing = false;
    }
  }
  $("upload").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      notice(t("notice.fileTooLarge"));
      return;
    }
    uploadBusy = true;
    $("generate-button").disabled = true;
    notice(t("reference.uploading"));
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error(t("notice.unreadableFile")));
        reader.readAsDataURL(file);
      });
      const asset = await bridge.apiPost("references", { data });
      await selectReference(asset);
      notice(t("reference.ready"));
    } catch (error) {
      notice(t("notice.uploadFailed", { message: reason(error) }));
    } finally {
      uploadBusy = false;
      $("generate-button").disabled = false;
    }
  });
  $("generate").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (uploadBusy) return;
    const prompt = $("prompt").value.trim();
    if (!prompt) return;
    if (/\{[^{}]+\}/.test(prompt)) {
      notice(t("notice.replaceVariables"));
      return;
    }
    const template = templates.find((item) => item.id === templateId);
    if (template && template.requires_reference && !reference) {
      notice(t("notice.templateNeedsReference"));
      return;
    }
    $("generate-button").disabled = true;
    try {
      const task = await bridge.apiPost("tasks", {
        prompt,
        size: $("size").value,
        image_count: Number($("image-count").value),
        reference: reference && reference.id,
        parent_id: parentId,
        template_id: templateId,
      });
      $("generate-status").textContent = t("notice.submittedDetail", { id: task.id });
      notice(t("notice.submitted"));
      page = 1;
      await refresh();
    } catch (error) {
      notice(t("notice.submitFailed", { message: reason(error) }));
    } finally {
      $("generate-button").disabled = false;
    }
  });
  document
    .querySelectorAll("[data-tab]")
    .forEach((el) => el.addEventListener("click", () => tab(el.dataset.tab)));
  $("clear-reference").addEventListener("click", clearReference);
  $("test-connection").addEventListener("click", async () => {
    const button = $("test-connection");
    button.disabled = true;
    try {
      const result = await bridge.apiPost("connectivity", {});
      notice(t("notice.connectionOk", { provider: result.provider || result.source, model: result.model || "-" }));
    } catch (error) {
      notice(t("notice.submitFailed", { message: reason(error) }));
    } finally {
      button.disabled = false;
    }
  });  $("refresh").addEventListener("click", refresh);
  $("category").addEventListener("change", renderTemplates);
  $("days").addEventListener("change", () => loadStats().catch((error) => notice(reason(error))));
  $("status-filter").addEventListener("change", () => {
    page = 1;
    void loadHistory().catch((error) => notice(reason(error)));
  });
  $("search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      page = 1;
      void loadHistory().catch((error) => notice(reason(error)));
    }, 300);
  });
  $("previous").addEventListener("click", () => {
    page--;
    void loadHistory().catch((error) => notice(reason(error)));
  });
  $("next").addEventListener("click", () => {
    page++;
    void loadHistory().catch((error) => notice(reason(error)));
  });

  /** Adopt a locale from the host and repaint everything already on screen. */
  function useLocale(next) {
    const chosen = String(next || "").toLowerCase().startsWith("zh") ? "zh" : "en";
    if (chosen === locale) return false;
    locale = chosen;
    return true;
  }

  function repaint() {
    applyStaticText();
    renderCategories();
    renderTemplates();
    if (reference) {
      $("generate-button").textContent = t("action.submitEdit");
      $("mode-title").textContent = t(parentId ? "create.continueHeading" : "create.editHeading");
    }
    // Force the cached renders to redraw in the new language.
    gallerySignature = "";
    historySignature = "";
    void refresh();
  }

  try {
    const context = await bridge.ready();
    useLocale(context && context.locale);
    applyStaticText();
    const data = await bridge.apiGet("templates");
    templates = data.items;
    renderCategories();
    renderTemplates();
    await refresh();
    // The reader can switch language while the page is open.
    bridge.onContext((next) => {
      if (useLocale(next && next.locale)) repaint();
    });
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    window.addEventListener(
      "pagehide",
      () => {
        clearInterval(timer);
        observer.disconnect();
      },
      { once: true },
    );
  } catch (error) {
    applyStaticText();
    notice(t("notice.initFailed", { message: reason(error) }));
  }
})();
