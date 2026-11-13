/* ==========================================================================
   La Casa Blanca · Gráficos interactivos SVG y acciones rápidas (PRB-19)
   Cero dependencias externas: funciona 100% offline en aula/laboratorio
   ========================================================================== */

(function () {
  "use strict";

  function escaparHtml(valor) {
    return String(valor).replace(/[&<>"']/g, function (caracter) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[caracter];
    });
  }

  const PALETA_DONUT = ["#3b82f6", "#eab308", "#0f4c5c", "#10b981", "#f97316", "#6366f1"];

  function obtenerTooltip() {
    let el = document.getElementById("chart-tooltip");
    if (!el) {
      el = document.createElement("div");
      el.id = "chart-tooltip";
      el.className = "chart-tooltip";
      document.body.appendChild(el);
    }
    return el;
  }

  function mostrarTooltip(evt, html) {
    const tip = obtenerTooltip();
    tip.innerHTML = html;
    tip.style.display = "block";
    tip.style.left = evt.clientX + 14 + "px";
    tip.style.top = evt.clientY - 12 + "px";
  }

  function ocultarTooltip() {
    const tip = document.getElementById("chart-tooltip");
    if (tip) tip.style.display = "none";
  }

  /* --- Gráfico 1: Barras Doradas (Cantidad de Platos por Categoría) --- */
  function renderBarrasPlatos() {
    const contenedor = document.getElementById("barras-platos-chart-container");
    const dataScript = document.getElementById("chart-categorias-data");
    if (!contenedor || !dataScript) return;

    let datos = [];
    try {
      datos = JSON.parse(dataScript.textContent || "[]");
    } catch (_) {
      datos = [];
    }

    if (!datos.length) {
      contenedor.innerHTML =
        '<div class="empty-state"><p>Registra categorías y platos para visualizar el gráfico.</p></div>';
      return;
    }

    const W = 540;
    const H = 260;
    const padL = 42;
    const padR = 24;
    const padT = 26;
    const padB = 48;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const maxTotalRaw = Math.max(...datos.map((d) => d.total || 0), 1);
    const yMax = maxTotalRaw <= 4 ? 4 : (maxTotalRaw % 2 === 0 ? maxTotalRaw : maxTotalRaw + 1);
    const pasos = 4;

    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.width = "100%";
    svg.style.height = "auto";

    // Líneas guía horizontales y etiquetas del eje Y (enteros)
    for (let i = 0; i <= pasos; i++) {
      const ratio = i / pasos;
      const y = padT + plotH - ratio * plotH;
      const val = Math.round(ratio * yMax);

      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", padL);
      line.setAttribute("x2", W - padR);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", "#eef2f7");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);

      const txt = document.createElementNS(ns, "text");
      txt.setAttribute("x", padL - 8);
      txt.setAttribute("y", y + 4);
      txt.setAttribute("text-anchor", "end");
      txt.setAttribute("fill", "#94a3b8");
      txt.setAttribute("font-size", "11");
      txt.setAttribute("font-family", "inherit");
      txt.textContent = String(val);
      svg.appendChild(txt);
    }

    const stepX = plotW / datos.length;
    const barW = Math.min(38, stepX * 0.46);

    datos.forEach((d, idx) => {
      const cx = padL + stepX * idx + stepX / 2;
      const hBarra = yMax > 0 ? (d.total / yMax) * plotH : 0;
      const yBarra = padT + plotH - hBarra;

      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("x", cx - barW / 2);
      rect.setAttribute("y", yBarra);
      rect.setAttribute("width", barW);
      rect.setAttribute("height", Math.max(hBarra, 3));
      rect.setAttribute("rx", "5");
      rect.setAttribute("fill", "#dfc05a");
      rect.style.cursor = "pointer";
      rect.style.transition = "opacity 0.15s ease";

      const infoHtml =
        `<strong>${escaparHtml(d.nombre)}</strong><br>` +
        `Platos registrados: <strong>${d.total}</strong><br>` +
        `• Disponibles: ${d.disponibles}<br>` +
        `• Agotados: ${d.agotados}`;

      rect.addEventListener("mouseenter", () => {
        rect.style.opacity = "0.85";
      });
      rect.addEventListener("mousemove", (e) => mostrarTooltip(e, infoHtml));
      rect.addEventListener("mouseleave", () => {
        rect.style.opacity = "1";
        ocultarTooltip();
      });
      svg.appendChild(rect);

      // Etiqueta de cantidad encima de cada barra
      if (d.total > 0) {
        const valTxt = document.createElementNS(ns, "text");
        valTxt.setAttribute("x", cx);
        valTxt.setAttribute("y", yBarra - 6);
        valTxt.setAttribute("text-anchor", "middle");
        valTxt.setAttribute("fill", "#786114");
        valTxt.setAttribute("font-size", "11");
        valTxt.setAttribute("font-weight", "600");
        valTxt.setAttribute("font-family", "inherit");
        valTxt.textContent = String(d.total);
        svg.appendChild(valTxt);
      }

      // Nombre de la categoría
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", cx);
      label.setAttribute("y", padT + plotH + 18);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("fill", "#64748b");
      label.setAttribute("font-size", "11");
      label.setAttribute("font-family", "inherit");
      const corto = d.nombre.length > 15 ? d.nombre.slice(0, 14) + "…" : d.nombre;
      label.textContent = corto;
      svg.appendChild(label);
    });

    contenedor.innerHTML = "";
    contenedor.appendChild(svg);
  }

  /* --- Gráfico 2: Curva Marina (Precio Promedio por Categoría en S/) --- */
  function renderCurvaPrecios() {
    const contenedor = document.getElementById("precio-promedio-chart-container");
    const dataScript = document.getElementById("chart-categorias-data");
    if (!contenedor || !dataScript) return;

    let datos = [];
    try {
      datos = JSON.parse(dataScript.textContent || "[]");
    } catch (_) {
      datos = [];
    }

    if (!datos.length) {
      contenedor.innerHTML =
        '<div class="empty-state"><p>Registra categorías y platos para visualizar los precios.</p></div>';
      return;
    }

    const W = 540;
    const H = 260;
    const padL = 58;
    const padR = 24;
    const padT = 26;
    const padB = 48;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const maxPrecioRaw = Math.max(...datos.map((d) => d.precio_promedio || 0), 10);
    const maxPrecio = Math.ceil(maxPrecioRaw / 10) * 10;
    const pasos = 4;

    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.width = "100%";
    svg.style.height = "auto";

    // Gradiente para sombra suave bajo la curva
    const defs = document.createElementNS(ns, "defs");
    const grad = document.createElementNS(ns, "linearGradient");
    grad.setAttribute("id", "grad-precio-marino");
    grad.setAttribute("x1", "0");
    grad.setAttribute("y1", "0");
    grad.setAttribute("x2", "0");
    grad.setAttribute("y2", "1");

    const stop1 = document.createElementNS(ns, "stop");
    stop1.setAttribute("offset", "0%");
    stop1.setAttribute("stop-color", "#0f4c5c");
    stop1.setAttribute("stop-opacity", "0.20");
    grad.appendChild(stop1);

    const stop2 = document.createElementNS(ns, "stop");
    stop2.setAttribute("offset", "100%");
    stop2.setAttribute("stop-color", "#0f4c5c");
    stop2.setAttribute("stop-opacity", "0.02");
    grad.appendChild(stop2);

    defs.appendChild(grad);
    svg.appendChild(defs);

    // Líneas guía horizontales y etiquetas Y (Soles)
    for (let i = 0; i <= pasos; i++) {
      const ratio = i / pasos;
      const y = padT + plotH - ratio * plotH;
      const val = Math.round(ratio * maxPrecio);

      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", padL);
      line.setAttribute("x2", W - padR);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", "#eef2f7");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);

      const txt = document.createElementNS(ns, "text");
      txt.setAttribute("x", padL - 8);
      txt.setAttribute("y", y + 4);
      txt.setAttribute("text-anchor", "end");
      txt.setAttribute("fill", "#94a3b8");
      txt.setAttribute("font-size", "11");
      txt.setAttribute("font-family", "inherit");
      txt.textContent = "S/ " + val;
      svg.appendChild(txt);
    }

    const stepX = plotW / datos.length;
    const puntos = [];

    datos.forEach((d, idx) => {
      const cx = padL + stepX * idx + stepX / 2;
      const ratioPrecio = maxPrecio > 0 ? (d.precio_promedio || 0) / maxPrecio : 0;
      const y = padT + plotH - ratioPrecio * plotH;

      const infoHtml =
        `<strong>${escaparHtml(d.nombre)}</strong><br>` +
        `Precio promedio: <strong>S/ ${Number(d.precio_promedio || 0).toFixed(2)}</strong>`;

      puntos.push({
        x: cx,
        y: y,
        precio: d.precio_promedio || 0,
        infoHtml: infoHtml,
      });

      // Nombre de la categoría
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", cx);
      label.setAttribute("y", padT + plotH + 18);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("fill", "#64748b");
      label.setAttribute("font-size", "11");
      label.setAttribute("font-family", "inherit");
      const corto = d.nombre.length > 15 ? d.nombre.slice(0, 14) + "…" : d.nombre;
      label.textContent = corto;
      svg.appendChild(label);
    });

    if (puntos.length > 0) {
      // Curva Bezier suave
      let curveD = `M ${puntos[0].x} ${puntos[0].y}`;
      for (let i = 0; i < puntos.length - 1; i++) {
        const p0 = puntos[i];
        const p1 = puntos[i + 1];
        const midX = (p0.x + p1.x) / 2;
        curveD += ` C ${midX} ${p0.y}, ${midX} ${p1.y}, ${p1.x} ${p1.y}`;
      }

      // Área rellena bajo la curva
      const baseY = padT + plotH;
      const areaD = `${curveD} L ${puntos[puntos.length - 1].x} ${baseY} L ${puntos[0].x} ${baseY} Z`;
      const areaPath = document.createElementNS(ns, "path");
      areaPath.setAttribute("d", areaD);
      areaPath.setAttribute("fill", "url(#grad-precio-marino)");
      svg.appendChild(areaPath);

      // Trazo de línea principal
      const linePath = document.createElementNS(ns, "path");
      linePath.setAttribute("d", curveD);
      linePath.setAttribute("fill", "none");
      linePath.setAttribute("stroke", "#0f4c5c");
      linePath.setAttribute("stroke-width", "2.8");
      svg.appendChild(linePath);

      // Puntos y etiquetas de valor en Soles
      puntos.forEach((pt) => {
        const circle = document.createElementNS(ns, "circle");
        circle.setAttribute("cx", pt.x);
        circle.setAttribute("cy", pt.y);
        circle.setAttribute("r", "5");
        circle.setAttribute("fill", "#ffffff");
        circle.setAttribute("stroke", "#0f4c5c");
        circle.setAttribute("stroke-width", "2.5");
        circle.style.cursor = "pointer";

        circle.addEventListener("mouseenter", () => {
          circle.setAttribute("r", "7");
        });
        circle.addEventListener("mousemove", (e) => mostrarTooltip(e, pt.infoHtml));
        circle.addEventListener("mouseleave", () => {
          circle.setAttribute("r", "5");
          ocultarTooltip();
        });
        svg.appendChild(circle);

        if (pt.precio > 0) {
          const valTxt = document.createElementNS(ns, "text");
          valTxt.setAttribute("x", pt.x);
          valTxt.setAttribute("y", pt.y - 9);
          valTxt.setAttribute("text-anchor", "middle");
          valTxt.setAttribute("fill", "#0f4c5c");
          valTxt.setAttribute("font-size", "10.5");
          valTxt.setAttribute("font-weight", "600");
          valTxt.setAttribute("font-family", "inherit");
          valTxt.textContent = "S/ " + Math.round(pt.precio);
          svg.appendChild(valTxt);
        }
      });
    }

    contenedor.innerHTML = "";
    contenedor.appendChild(svg);
  }

  /* Compatibilidad con invocaciones heredadas */
  function renderComboCategorias() {
    renderBarrasPlatos();
    renderCurvaPrecios();
  }

  /* --- Gráfico 2: Donut Interactivo (Disponibilidad / Categorías) --- */
  function renderDonut(modo) {
    const contenedor = document.getElementById("donut-chart-container");
    const leyendaEl = document.getElementById("donut-legend");
    const dataScript = document.getElementById("chart-donut-data");
    if (!contenedor || !dataScript) return;

    let raw = {};
    try {
      raw = JSON.parse(dataScript.textContent || "{}");
    } catch (_) {
      raw = {};
    }

    const items =
      modo === "categorias"
        ? (raw.por_categoria || []).map((it, i) => ({
            label: it.label,
            value: it.value,
            color: PALETA_DONUT[i % PALETA_DONUT.length],
          }))
        : raw.disponibilidad || [];

    const total = items.reduce((acc, it) => acc + (it.value || 0), 0);
    if (!total) {
      contenedor.innerHTML =
        '<div class="empty-state"><p>Sin platos para graficar distribución.</p></div>';
      if (leyendaEl) leyendaEl.innerHTML = "";
      return;
    }

    const size = 215;
    const cx = size / 2;
    const cy = size / 2;
    const r = 74;
    const circunf = 2 * Math.PI * r;

    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.style.width = "215px";
    svg.style.height = "215px";

    let acumulado = 0;
    items.forEach((it) => {
      if (!it.value) return;
      const frac = it.value / total;
      const dash = Math.max(frac * circunf - 2.5, 1);
      const circle = document.createElementNS(ns, "circle");
      circle.setAttribute("cx", cx);
      circle.setAttribute("cy", cy);
      circle.setAttribute("r", r);
      circle.setAttribute("fill", "transparent");
      circle.setAttribute("stroke", it.color);
      circle.setAttribute("stroke-width", "28");
      circle.setAttribute("stroke-dasharray", `${dash} ${circunf}`);
      circle.setAttribute("stroke-dashoffset", String(-acumulado * circunf));
      circle.setAttribute("transform", `rotate(-90 ${cx} ${cy})`);
      circle.style.cursor = "pointer";

      const pct = ((it.value / total) * 100).toFixed(1);
      circle.addEventListener("mousemove", (e) =>
        mostrarTooltip(
          e,
          `<strong>${escaparHtml(it.label)}</strong>: ${it.value} (${pct}%)`
        )
      );
      circle.addEventListener("mouseleave", ocultarTooltip);
      svg.appendChild(circle);
      acumulado += frac;
    });

    const txtValor = document.createElementNS(ns, "text");
    txtValor.setAttribute("x", cx);
    txtValor.setAttribute("y", cy - 2);
    txtValor.setAttribute("text-anchor", "middle");
    txtValor.setAttribute("fill", "#0f172a");
    txtValor.setAttribute("font-size", "22");
    txtValor.setAttribute("font-weight", "700");
    txtValor.textContent = String(total);
    svg.appendChild(txtValor);

    const txtSub = document.createElementNS(ns, "text");
    txtSub.setAttribute("x", cx);
    txtSub.setAttribute("y", cy + 16);
    txtSub.setAttribute("text-anchor", "middle");
    txtSub.setAttribute("fill", "#64748b");
    txtSub.setAttribute("font-size", "11");
    txtSub.textContent = "platos";
    svg.appendChild(txtSub);

    contenedor.innerHTML = "";
    contenedor.appendChild(svg);

    if (leyendaEl) {
      leyendaEl.innerHTML = items
        .map((it) => {
          const color = /^#[0-9a-fA-F]{6}$/.test(it.color)
            ? it.color
            : "#64748b";
          return (
            `<span class="legend-item">` +
            `<span class="legend-swatch" style="background:${color}"></span>` +
            `${escaparHtml(it.label)} (${it.value})` +
            `</span>`
          );
        })
        .join("");
    }
  }

  /* --- Actualización en vivo de KPIs cuando se usa switch AJAX --- */
  function actualizarKpisDom(kpis) {
    if (!kpis) return;
    const setTxt = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };
    setTxt("kpi-total-platos", kpis.total_platos);
    setTxt("kpi-disponibles", kpis.platos_disponibles);
    setTxt("kpi-agotados", kpis.platos_agotados);
    setTxt("kpi-pct-disponibles", kpis.pct_disponibles + "%");
    setTxt("kpi-pct-agotados", kpis.pct_agotados + "%");
    if (typeof kpis.precio_promedio === "number") {
      setTxt("kpi-precio-promedio", "S/ " + kpis.precio_promedio.toFixed(2));
    }
  }

  /* --- Switches AJAX para Pesca del Día --- */
  function inicializarSwitchesAjax() {
    document.querySelectorAll("form[data-ajax-toggle='true']").forEach((form) => {
      form.addEventListener("submit", async function (evt) {
        evt.preventDefault();
        const btn = form.querySelector(".switch-btn");
        const badge = document.querySelector(`[data-status-badge="${form.dataset.platoId}"]`);
        const csrf = form.querySelector("input[name='csrfmiddlewaretoken']");
        if (!csrf) {
          form.submit();
          return;
        }
        try {
          const resp = await fetch(form.action, {
            method: "POST",
            headers: {
              "X-CSRFToken": csrf.value,
              Accept: "application/json",
            },
            body: new FormData(form),
          });
          if (!resp.ok) throw new Error("Error HTTP");
          const data = await resp.json();
          if (btn) {
            btn.classList.toggle("is-on", data.disponible);
            btn.setAttribute("aria-pressed", data.disponible ? "true" : "false");
          }
          if (badge) {
            badge.className =
              "status-badge " + (data.disponible ? "is-available" : "is-soldout");
            badge.textContent = data.disponible ? "Disponible" : "Agotado";
          }
          actualizarKpisDom(data.kpis);
        } catch (_) {
          form.submit();
        }
      });
    });
  }

  /* --- Modales y Selección Masiva --- */
  function inicializarModalesYLotes() {
    document.querySelectorAll("[data-open-modal]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const target = document.getElementById(trigger.dataset.openModal);
        if (target) target.classList.add("is-open");
      });
    });

    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const modal = btn.closest(".modal-backdrop");
        if (modal) modal.classList.remove("is-open");
      });
    });

    document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) backdrop.classList.remove("is-open");
      });
    });

    const checkAll = document.getElementById("select-all-platos");
    if (checkAll) {
      checkAll.addEventListener("change", () => {
        document.querySelectorAll(".plato-row-check").forEach((chk) => {
          chk.checked = checkAll.checked;
        });
      });
    }

    document.querySelectorAll("[data-donut-mode]").forEach((tab) => {
      tab.addEventListener("click", () => {
        document
          .querySelectorAll("[data-donut-mode]")
          .forEach((t) => t.classList.remove("is-active"));
        tab.classList.add("is-active");
        renderDonut(tab.dataset.donutMode);
      });
    });
  }

  /* --- Sondeo Simple del Dashboard Operativo (PRB-45) --- */
  function iniciarPollingOperativo() {
    const btnRefrescar = document.getElementById("btn-refrescar-operativo");
    const container = document.querySelector(".operativo-panel");
    if (!container) return;

    async function refrescarOperativo() {
      try {
        const resp = await fetch("/operativo/kpis/", {
          headers: { Accept: "application/json" },
        });
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data || !data.ok) return;

        const setVal = (id, val) => {
          const el = document.getElementById(id);
          if (el) el.textContent = val;
        };

        setVal("op-kpi-mesas-ocupadas", data.mesas_ocupadas);
        setVal("op-kpi-total-mesas", data.total_mesas);
        setVal("op-kpi-mesas-libres", data.mesas_libres);
        setVal("op-kpi-mesas-cuenta", data.mesas_pide_cuenta);
        setVal("op-pct-ocupadas", data.pct_mesas_ocupadas + "% ocupación");
        setVal("op-kpi-ventas-dia", data.ventas_dia);
        setVal("op-badge-ventas", data.pedidos_cobrados_hoy + " cobradas");
        setVal("op-kpi-platos-agotados", data.platos_agotados);
        setVal("op-kpi-pedidos-pendientes", data.pedidos_pendientes);

        const badgeAgotados = document.getElementById("op-badge-agotados");
        if (badgeAgotados) {
          badgeAgotados.className =
            "op-kpi-badge " + (data.platos_agotados > 0 ? "warn" : "up");
          badgeAgotados.textContent =
            data.platos_agotados > 0 ? "Atención insumo" : "Stock activo";
        }

        const badgePedidos = document.getElementById("op-badge-pedidos");
        if (badgePedidos) {
          badgePedidos.className =
            "op-kpi-badge " + (data.pedidos_pendientes > 0 ? "warn" : "up");
          badgePedidos.textContent =
            data.pedidos_pendientes > 0 ? "En preparación" : "Al día";
        }

        const ts = document.getElementById("operativo-timestamp");
        if (ts && data.hora) {
          ts.textContent = "Actualizado: " + data.hora;
        }

        if (Array.isArray(data.mesas)) {
          data.mesas.forEach((m) => {
            const mesaEl = document.querySelector(`[data-mesa-num="${m.numero}"]`);
            if (mesaEl) {
              mesaEl.className = `mesa-box mesa-estado-${m.estado.toLowerCase()}`;
              const pill = mesaEl.querySelector(".mesa-status-pill");
              if (pill) {
                pill.textContent = m.estado_display || m.estado;
              }
            }
          });
        }
      } catch (_) {
        // En caso de corte momentáneo de red, continuar
      }
    }

    if (btnRefrescar) {
      btnRefrescar.addEventListener("click", function () {
        btnRefrescar.disabled = true;
        btnRefrescar.style.opacity = "0.6";
        refrescarOperativo().finally(() => {
          setTimeout(() => {
            btnRefrescar.disabled = false;
            btnRefrescar.style.opacity = "1";
          }, 600);
        });
      });
    }

    // Sondeo simple cada 30 segundos (sin WebSocket, cumple PRB-45)
    setInterval(refrescarOperativo, 30000);
  }

  function initPanel() {
    renderBarrasPlatos();
    renderCurvaPrecios();
    renderDonut("categorias");
    inicializarSwitchesAjax();
    inicializarModalesYLotes();
    iniciarPollingOperativo();
  }

  // Exportar para acceso seguro
  window.renderBarrasPlatos = renderBarrasPlatos;
  window.renderCurvaPrecios = renderCurvaPrecios;
  window.renderDonut = renderDonut;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPanel);
  } else {
    initPanel();
  }
})();
