/* ==========================================================================
   La Casa Blanca · Gráficos interactivos SVG y acciones rápidas (PRB-19)
   Cero dependencias externas: funciona 100% offline en aula/laboratorio
   ========================================================================== */

(function () {
  "use strict";

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

  /* --- Gráfico 1: Barras Doradas (Platos) + Curva Marina (Precio Promedio S/) --- */
  function renderComboCategorias() {
    const contenedor = document.getElementById("combo-chart-container");
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
        '<div class="empty-state"><p>Registra categorías y platos para visualizar la comparativa.</p></div>';
      return;
    }

    const W = 680;
    const H = 265;
    const padL = 56;
    const padR = 46;
    const padT = 18;
    const padB = 54;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const maxPrecioRaw = Math.max(...datos.map((d) => d.precio_promedio || 0), 10);
    const maxPrecio = Math.ceil(maxPrecioRaw / 10) * 10;
    const maxPlatos = Math.max(...datos.map((d) => d.total || 0), 4);

    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.width = "100%";
    svg.style.height = "auto";

    const pasos = 5;
    for (let i = 0; i <= pasos; i++) {
      const ratio = i / pasos;
      const y = padT + plotH - ratio * plotH;

      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", padL);
      line.setAttribute("x2", W - padR);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", "#eef2f7");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);

      const txtIzq = document.createElementNS(ns, "text");
      txtIzq.setAttribute("x", padL - 8);
      txtIzq.setAttribute("y", y + 4);
      txtIzq.setAttribute("text-anchor", "end");
      txtIzq.setAttribute("fill", "#94a3b8");
      txtIzq.setAttribute("font-size", "10.5");
      txtIzq.textContent = "S/ " + Math.round(ratio * maxPrecio);
      svg.appendChild(txtIzq);

      const txtDer = document.createElementNS(ns, "text");
      txtDer.setAttribute("x", W - padR + 8);
      txtDer.setAttribute("y", y + 4);
      txtDer.setAttribute("text-anchor", "start");
      txtDer.setAttribute("fill", "#94a3b8");
      txtDer.setAttribute("font-size", "10.5");
      txtDer.textContent = (ratio * maxPlatos).toFixed(1);
      svg.appendChild(txtDer);
    }

    const stepX = plotW / datos.length;
    const barW = Math.min(34, stepX * 0.42);
    const puntosLinea = [];

    datos.forEach((d, idx) => {
      const cx = padL + stepX * idx + stepX / 2;
      const hBarra = (d.total / maxPlatos) * plotH;
      const yBarra = padT + plotH - hBarra;

      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("x", cx - barW / 2);
      rect.setAttribute("y", yBarra);
      rect.setAttribute("width", barW);
      rect.setAttribute("height", Math.max(hBarra, 2));
      rect.setAttribute("rx", "5");
      rect.setAttribute("fill", "#dfc05a");
      rect.style.cursor = "pointer";

      const infoHtml =
        `<strong>${d.nombre}</strong><br>` +
        `Platos totales: ${d.total} (${d.disponibles} disp. / ${d.agotados} agot.)<br>` +
        `Precio promedio: S/ ${Number(d.precio_promedio).toFixed(2)}`;

      rect.addEventListener("mousemove", (e) => mostrarTooltip(e, infoHtml));
      rect.addEventListener("mouseleave", ocultarTooltip);
      svg.appendChild(rect);

      const yPrecio = padT + plotH - ((d.precio_promedio || 0) / maxPrecio) * plotH;
      puntosLinea.push({ x: cx, y: yPrecio, infoHtml: infoHtml });

      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", cx);
      label.setAttribute("y", padT + plotH + 20);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("fill", "#64748b");
      label.setAttribute("font-size", "11");
      const corto = d.nombre.length > 16 ? d.nombre.slice(0, 15) + "…" : d.nombre;
      label.textContent = corto;
      svg.appendChild(label);
    });

    if (puntosLinea.length > 0) {
      let pathD = `M ${puntosLinea[0].x} ${puntosLinea[0].y}`;
      for (let i = 0; i < puntosLinea.length - 1; i++) {
        const p0 = puntosLinea[i];
        const p1 = puntosLinea[i + 1];
        const midX = (p0.x + p1.x) / 2;
        pathD += ` C ${midX} ${p0.y}, ${midX} ${p1.y}, ${p1.x} ${p1.y}`;
      }
      const path = document.createElementNS(ns, "path");
      path.setAttribute("d", pathD);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "#0f4c5c");
      path.setAttribute("stroke-width", "2.6");
      svg.appendChild(path);

      puntosLinea.forEach((pt) => {
        const circle = document.createElementNS(ns, "circle");
        circle.setAttribute("cx", pt.x);
        circle.setAttribute("cy", pt.y);
        circle.setAttribute("r", "4.5");
        circle.setAttribute("fill", "#ffffff");
        circle.setAttribute("stroke", "#0f4c5c");
        circle.setAttribute("stroke-width", "2.5");
        circle.style.cursor = "pointer";
        circle.addEventListener("mousemove", (e) => mostrarTooltip(e, pt.infoHtml));
        circle.addEventListener("mouseleave", ocultarTooltip);
        svg.appendChild(circle);
      });
    }

    contenedor.innerHTML = "";
    contenedor.appendChild(svg);
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
        mostrarTooltip(e, `<strong>${it.label}</strong>: ${it.value} (${pct}%)`)
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
        .map(
          (it) =>
            `<span class="legend-item">` +
            `<span class="legend-swatch" style="background:${it.color}"></span>` +
            `${it.label} (${it.value})` +
            `</span>`
        )
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

  document.addEventListener("DOMContentLoaded", function () {
    renderComboCategorias();
    renderDonut("categorias");
    inicializarSwitchesAjax();
    inicializarModalesYLotes();
  });
})();
