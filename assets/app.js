const metricMap = {
  international_gold: "gold.international",
  shanghai_gold: "gold.shanghai",
  eur_cny: "fx.eur_cny",
  usd_cny: "fx.usd_cny",
  btc_cny: "crypto.btc_cny",
  btc_usd: "crypto.btc_usd",
};

const formatters = {
  gold: new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }),
  fx: new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }),
  crypto: new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }),
};

function getNestedValue(record, path) {
  if (!path) {
    return undefined;
  }

  return path.split(".").reduce((value, key) => value?.[key], record);
}

function formatValue(metric) {
  const formatter = formatters[metric.category] || formatters.fx;
  return `${formatter.format(metric.value)} ${metric.unit}`;
}

function formatChange(metric) {
  if (metric.change_abs == null || metric.change_pct == null) {
    return { text: `${metric.change_basis || "较上次抓取"} 无对比数据`, state: "flat" };
  }

  const sign = metric.change_abs > 0 ? "+" : "";
  const formatter = formatters[metric.category] || formatters.fx;
  return {
    text: `${metric.change_basis || "较上次抓取"} ${sign}${formatter.format(metric.change_abs)} (${sign}${metric.change_pct.toFixed(2)}%)`,
    state: metric.change_abs > 0 ? "up" : metric.change_abs < 0 ? "down" : "flat",
  };
}

function formatMeta(metric) {
  return `${metric.market_time} · ${metric.source_note}`;
}

function renderSparkline(target, points) {
  if (!points || points.length === 0) {
    target.textContent = "暂无趋势数据";
    return;
  }

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = 320;
  const height = 92;
  const padding = 10;
  const range = max - min || 1;

  const coords = points.map((point, index) => {
    const x = padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - ((point.value - min) / range) * (height - padding * 2);
    return [x, y];
  });

  const linePath = coords
    .map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L ${coords.at(-1)[0].toFixed(2)} ${(height - padding).toFixed(2)} L ${coords[0][0].toFixed(2)} ${(height - padding).toFixed(2)} Z`;

  target.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="最近趋势">
      <defs>
        <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(21,61,100,0.30)"></stop>
          <stop offset="100%" stop-color="rgba(21,61,100,0)"></stop>
        </linearGradient>
      </defs>
      <path class="area" d="${areaPath}"></path>
      <path class="line" d="${linePath}"></path>
    </svg>
  `;
}

function renderSources(sources) {
  const list = document.getElementById("sourceList");
  const template = document.getElementById("sourceItemTemplate");
  list.innerHTML = "";

  sources.forEach((source) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".source-name").textContent = source.label;
    const link = node.querySelector(".source-link");
    link.href = source.url;
    list.appendChild(node);
  });
}

function updateHeader(latest) {
  const status = document.getElementById("globalStatus");
  const publishedAt = document.getElementById("publishedAt");
  status.textContent = `准实时模式 · 后端约每 ${Math.round((latest.refresh_interval_seconds || 300) / 60)} 分钟刷新`;
  publishedAt.textContent = `最新抓取：${latest.published_at} · 前端每 ${Math.round((latest.ui_poll_interval_seconds || 60) / 60) || 1} 分钟检查更新`;
}

function renderCards(latest, history) {
  document.querySelectorAll(".metric-card").forEach((card) => {
    const seriesKey = card.dataset.seriesKey;
    const metricPath = metricMap[seriesKey];
    if (!metricPath) {
      return;
    }

    const metric = getNestedValue(latest, metricPath);
    const series = history.series[seriesKey] || [];

    if (!metric) {
      card.querySelector('[data-field="secondary"]').textContent = "当前无数据";
      return;
    }

    card.querySelector('[data-field="value"]').textContent = formatValue(metric);

    const change = formatChange(metric);
    const changeNode = card.querySelector('[data-field="change"]');
    changeNode.textContent = change.text;
    changeNode.className = `metric-change ${change.state}`;

    const secondaryNode = card.querySelector('[data-field="secondary"]');
    secondaryNode.textContent = metric.secondary_value || "";

    card.querySelector('[data-field="meta"]').textContent = formatMeta(metric);
    const sourceLink = card.querySelector('[data-field="source"]');
    sourceLink.href = metric.source_url;
    sourceLink.textContent = metric.source_name;

    renderSparkline(card.querySelector('[data-field="sparkline"]'), series);
  });
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}`);
  }

  return response.json();
}

async function boot() {
  try {
    const [latest, history] = await Promise.all([
      loadJson("./data/latest.json"),
      loadJson("./data/history.json"),
    ]);
    updateHeader(latest);
    renderCards(latest, history);
    renderSources(latest.sources || []);
  } catch (error) {
    document.getElementById("globalStatus").textContent = "数据加载失败";
    document.getElementById("publishedAt").textContent = String(error);
  }
}

boot();
window.setInterval(boot, 60_000);
