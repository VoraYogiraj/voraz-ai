/**
 * VORA Quiz Engine
 * Renders branching chip/toggle quiz from /api/quiz/questions config,
 * persists each answer immediately (for resumability), and renders
 * final product results with match_reason + order-type-specific CTA.
 *
 * Depends on: window.VORA_CONFIG.apiBase (set by vora-ai-stylist.liquid)
 * Mount point: an element with [data-vora-quiz] in the DOM.
 */

(function () {
  "use strict";

  const STORAGE_KEY = "vora_quiz_session_token";
  const API_BASE = (window.VORA_CONFIG && window.VORA_CONFIG.apiBase) || "";

  class VoraQuiz {
    constructor(root, opts = {}) {
      this.root = root;
      this.opts = opts;
      this.config = null;
      this.sessionToken = localStorage.getItem(STORAGE_KEY) || null;
      this.answers = {};
      this.currentStepId = null;
      this.orderType = null;

      this.init();
    }

    async init() {
      this.renderLoading();
      try {
        this.config = await this.fetchJSON("/api/quiz/questions", { method: "GET" });
      } catch (e) {
        this.renderError("Couldn't load the quiz. Please refresh.");
        return;
      }

      if (this.sessionToken) {
        try {
          const resumed = await this.fetchJSON(`/api/quiz/resume/${this.sessionToken}`, { method: "GET" });
          this.answers = resumed.quiz_answers || {};
          this.orderType = this.answers.order_type || null;
          if (resumed.quiz_completed) {
            this.sessionToken = null;
            localStorage.removeItem(STORAGE_KEY);
            this.answers = {};
          } else if (resumed.quiz_step) {
            this.currentStepId = this.nextStepAfter(resumed.quiz_step);
          }
        } catch (e) {
          this.sessionToken = null;
          localStorage.removeItem(STORAGE_KEY);
        }
      }

      if (this.opts.mode === "product" && this.opts.prefillProductId && !this.orderType) {
        try {
          const prefill = await this.fetchJSON(`/api/quiz/prefill/${this.opts.prefillProductId}`, { method: "GET" });
          Object.keys(prefill).forEach((k) => {
            if (prefill[k] !== null && prefill[k] !== undefined && prefill[k] !== "") {
              this.answers[k] = prefill[k];
            }
          });
          this.orderType = this.answers.order_type || null;
        } catch (e) {
          // Prefill is a nice-to-have; silently continue with a blank quiz.
        }
      }

      if (!this.currentStepId) {
        this.currentStepId = "order_type";
      }

      this.renderStep(this.currentStepId);
    }

    getFlow() {
      if (!this.orderType) return null;
      return this.config.flow[this.orderType] || null;
    }

    nextStepAfter(stepId) {
      const flow = this.getFlow();
      if (!flow) return "order_type";
      const idx = flow.indexOf(stepId);
      if (idx === -1 || idx === flow.length - 1) return stepId;
      return flow[idx + 1];
    }

    getQuestion(id) {
      return this.config.questions.find((q) => q.id === id);
    }

    shouldShowField(field) {
      if (!field.show_for || field.show_for === "all") return true;
      if (Array.isArray(field.show_for)) return field.show_for.includes(this.orderType);
      return false;
    }

    async fetchJSON(path, opts) {
      const res = await fetch(API_BASE + path, {
        headers: { "Content-Type": "application/json" },
        ...opts,
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      return res.json();
    }

    async saveAnswer(questionId, value) {
      const body = {
        session_token: this.sessionToken,
        question_id: questionId,
        value,
      };
      const res = await this.fetchJSON("/api/quiz/answer", {
        method: "POST",
        body: JSON.stringify(body),
      });
      this.sessionToken = res.session_token;
      localStorage.setItem(STORAGE_KEY, this.sessionToken);
      this.answers[questionId] = value;
    }

    async fetchResults() {
      return this.fetchJSON("/api/quiz/results", {
        method: "POST",
        body: JSON.stringify({ session_token: this.sessionToken }),
      });
    }

    renderLoading() {
      this.root.innerHTML = `<div class="vq-loading">Loading your style quiz…</div>`;
    }

    renderError(msg) {
      this.root.innerHTML = `<div class="vq-error">${this.escape(msg)}</div>`;
    }

    escape(str) {
      const div = document.createElement("div");
      div.textContent = str == null ? "" : String(str);
      return div.innerHTML;
    }

    renderProgress(stepId) {
      const flow = this.getFlow() || ["order_type"];
      const idx = Math.max(flow.indexOf(stepId), 0);
      const pct = Math.round(((idx + 1) / flow.length) * 100);
      return `
        <div class="vq-progress">
          <div class="vq-progress-bar" style="width:${pct}%"></div>
        </div>
        <div class="vq-progress-label">Step ${idx + 1} of ${flow.length}</div>
      `;
    }

    renderStep(stepId) {
      const question = this.getQuestion(stepId);
      if (!question) {
        this.renderError("Something went wrong loading this step.");
        return;
      }

      const progressHtml = stepId === "order_type" ? "" : this.renderProgress(stepId);

      if (question.type === "single_select") {
        this.renderSingleSelect(question, progressHtml);
      } else if (question.type === "multi_select") {
        this.renderMultiSelect(question, progressHtml);
      } else if (question.type === "lead_form") {
        this.renderLeadForm(question, progressHtml);
      } else if (question.type === "results") {
        this.renderResults(question, progressHtml);
      }
    }

    renderSingleSelect(question, progressHtml) {
      const optionsHtml = question.options
        .map(
          (opt) => `
        <button class="vq-chip" data-value="${this.escape(opt.value)}" type="button">
          <span class="vq-chip-label">${this.escape(opt.label)}</span>
          ${opt.sublabel ? `<span class="vq-chip-sublabel">${this.escape(opt.sublabel)}</span>` : ""}
        </button>
      `
        )
        .join("");

      this.root.innerHTML = `
        ${progressHtml}
        <div class="vq-step">
          <h3 class="vq-title">${this.escape(question.title)}</h3>
          ${question.sublabel ? `<p class="vq-sublabel">${this.escape(question.sublabel)}</p>` : ""}
          <div class="vq-chip-grid">${optionsHtml}</div>
          ${question.optional ? `<button class="vq-skip" type="button">Skip</button>` : ""}
          ${this.backButtonHtml(question)}
        </div>
      `;

      this.root.querySelectorAll(".vq-chip").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const value = btn.getAttribute("data-value");
          if (question.id === "order_type") this.orderType = value;
          this.setBusy(true);
          try {
            await this.saveAnswer(question.id, value);
            this.advance(question.id);
          } catch (e) {
            this.setBusy(false);
            this.renderError("Couldn't save your answer — check your connection and try again.");
          }
        });
      });

      const skipBtn = this.root.querySelector(".vq-skip");
      if (skipBtn) {
        skipBtn.addEventListener("click", async () => {
          this.setBusy(true);
          try {
            await this.saveAnswer(question.id, null);
            this.advance(question.id);
          } catch (e) {
            this.setBusy(false);
            this.renderError("Couldn't save — check your connection and try again.");
          }
        });
      }

      this.wireBackButton(question);
    }

    renderMultiSelect(question, progressHtml) {
      const min = question.min_select || 1;
      const max = question.max_select || question.options.length;
      const selected = new Set(
        Array.isArray(this.answers[question.id]) ? this.answers[question.id] : []
      );

      const renderChips = () =>
        question.options
          .map((opt) => {
            const isActive = selected.has(opt.value);
            return `
          <button class="vq-chip ${isActive ? "vq-chip-active" : ""}" data-value="${this.escape(
              opt.value
            )}" type="button">
            <span class="vq-chip-label">${this.escape(opt.label)}</span>
          </button>
        `;
          })
          .join("");

      this.root.innerHTML = `
        ${progressHtml}
        <div class="vq-step">
          <h3 class="vq-title">${this.escape(question.title)}</h3>
          ${question.sublabel ? `<p class="vq-sublabel">${this.escape(question.sublabel)}</p>` : ""}
          <div class="vq-chip-grid" data-multi-grid>${renderChips()}</div>
          <button class="vq-next" type="button" disabled>Continue</button>
          ${this.backButtonHtml(question)}
        </div>
      `;

      const grid = this.root.querySelector("[data-multi-grid]");
      const nextBtn = this.root.querySelector(".vq-next");

      const refreshNextState = () => {
        nextBtn.disabled = selected.size < min;
      };
      refreshNextState();

      grid.querySelectorAll(".vq-chip").forEach((btn) => {
        btn.addEventListener("click", () => {
          const value = btn.getAttribute("data-value");
          if (selected.has(value)) {
            selected.delete(value);
            btn.classList.remove("vq-chip-active");
          } else {
            if (selected.size >= max) return;
            selected.add(value);
            btn.classList.add("vq-chip-active");
          }
          refreshNextState();
        });
      });

      nextBtn.addEventListener("click", async () => {
        this.setBusy(true);
        try {
          await this.saveAnswer(question.id, Array.from(selected));
          this.advance(question.id);
        } catch (e) {
          this.setBusy(false);
          this.renderError("Couldn't save your answer — check your connection and try again.");
        }
      });

      this.wireBackButton(question);
    }

    renderLeadForm(question, progressHtml) {
      const fields = question.fields.filter((f) => this.shouldShowField(f));

      const fieldHtml = (f) => {
        if (f.type === "image_or_url") {
          return `
            <div class="vq-field">
              <label class="vq-label">${this.escape(f.label)}${f.required ? " *" : ""}</label>
              <input class="vq-input" type="url" name="${f.id}" placeholder="Paste a link (Pinterest, Instagram, etc.)" />
              <input class="vq-input-file" type="file" name="${f.id}_file" accept="image/*" />
            </div>
          `;
        }
        return `
          <div class="vq-field">
            <label class="vq-label">${this.escape(f.label)}${f.required ? " *" : ""}</label>
            <input class="vq-input" type="${f.type}" name="${f.id}" ${f.required ? "required" : ""} />
          </div>
        `;
      };

      this.root.innerHTML = `
        ${progressHtml}
        <div class="vq-step">
          <h3 class="vq-title">${this.escape(question.title)}</h3>
          <form class="vq-lead-form" data-lead-form>
            ${fields.map(fieldHtml).join("")}
            <button class="vq-next" type="submit">See my matches</button>
          </form>
          ${this.backButtonHtml(question)}
        </div>
      `;

      const form = this.root.querySelector("[data-lead-form]");
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const lead = {};
        fields.forEach((f) => {
          if (f.type === "image_or_url") {
            lead.inspiration = { url: formData.get(f.id) || null, image_url: null };
          } else {
            lead[f.id] = formData.get(f.id);
          }
        });

        const missingRequired = fields.some((f) => {
          if (f.type === "image_or_url") return f.required && !lead.inspiration.url;
          return f.required && !lead[f.id];
        });
        if (missingRequired) {
          this.renderInlineError(form, "Please fill in all required fields.");
          return;
        }

        this.setBusy(true);
        try {
          await this.saveAnswer(question.id, lead);
          this.advance(question.id);
        } catch (err) {
          this.setBusy(false);
          this.renderInlineError(form, "Couldn't save — check your connection and try again.");
        }
      });

      this.wireBackButton(question);
    }

    renderResults(question, progressHtml) {
      this.root.innerHTML = `${progressHtml}<div class="vq-step vq-results-loading">Finding your matches…</div>`;

      this.fetchResults()
        .then((data) => {
          const cta = data.cta || {};
          const loosenedNotice =
            data.loosened && data.loosened.length
              ? `<div class="vq-loosened-notice">We broadened your ${data.loosened.join(
                  " and "
                )} to show you more options.</div>`
              : "";

          if (data.order_type === "fully_bespoke") {
            this.root.innerHTML = `
              <div class="vq-step vq-results">
                <h3 class="vq-title">${this.escape(question.title)}</h3>
                <p class="vq-bespoke-msg">
                  Thanks — a stylist will reach out to design this with you from scratch.
                </p>
                ${
                  cta.whatsapp_link
                    ? `<a class="vq-cta" href="${this.escape(cta.whatsapp_link)}" target="_blank" rel="noopener">${this.escape(
                        cta.label || "Chat with a Stylist"
                      )}</a>`
                    : ""
                }
              </div>
            `;
            return;
          }

          const cardsHtml = (data.products || [])
            .map((p) => this.renderProductCard(p, cta))
            .join("");

          this.root.innerHTML = `
            <div class="vq-step vq-results">
              <h3 class="vq-title">${this.escape(question.title)}</h3>
              ${loosenedNotice}
              <div class="vw-product-grid">${cardsHtml || `<p class="vq-empty">No matches yet — a stylist can help you find the right fit.</p>`}</div>
              ${
                cta.action === "whatsapp_handoff" && cta.whatsapp_link
                  ? `<a class="vq-cta vq-cta-sticky" href="${this.escape(cta.whatsapp_link)}" target="_blank" rel="noopener">${this.escape(
                      cta.label || "Chat with a Stylist"
                    )}</a>`
                  : ""
              }
            </div>
          `;

          if (cta.action === "add_to_cart") {
            this.root.querySelectorAll("[data-add-to-cart]").forEach((btn) => {
              btn.addEventListener("click", () => {
                const url = btn.getAttribute("data-product-url");
                if (url) window.location.href = url;
              });
            });
          }
        })
        .catch(() => {
          this.renderError("Couldn't load your matches. Please try again.");
        });
    }

    renderProductCard(product, cta) {
      const image = (product.image_urls && product.image_urls[0]) || "";
      const price = product.starting_price_inr || product.price_inr;
      const priceLabel = price
        ? `${product.starting_price_inr ? "From " : ""}₹${Number(price).toLocaleString("en-IN")}`
        : "Price on request";

      const ctaHtml =
        cta.action === "add_to_cart"
          ? `<button class="vw-product-card-cta" data-add-to-cart data-product-url="${this.escape(
              product.product_url || "#"
            )}" type="button">${this.escape(cta.label || "View")}</button>`
          : `<a class="vw-product-card-cta" href="${this.escape(product.product_url || "#")}" target="_blank" rel="noopener">${this.escape(
              cta.label || "View"
            )}</a>`;

      return `
        <div class="vw-product-card">
          ${image ? `<img class="vw-product-card-img" src="${this.escape(image)}" alt="${this.escape(product.title || "")}" />` : ""}
          <div class="vw-product-card-body">
            <div class="vw-product-card-title">${this.escape(product.title || "")}</div>
            <div class="vw-product-card-price">${priceLabel}</div>
            ${product.match_reason ? `<div class="vw-product-card-reason">${this.escape(product.match_reason)}</div>` : ""}
            ${ctaHtml}
          </div>
        </div>
      `;
    }

    backButtonHtml(question) {
      const flow = this.getFlow();
      if (!flow || question.id === "order_type") return "";
      const idx = flow.indexOf(question.id);
      if (idx <= 0) return "";
      return `<button class="vq-back" type="button">Back</button>`;
    }

    wireBackButton(question) {
      const backBtn = this.root.querySelector(".vq-back");
      if (!backBtn) return;
      backBtn.addEventListener("click", () => {
        const flow = this.getFlow();
        const idx = flow.indexOf(question.id);
        if (idx > 0) this.renderStep(flow[idx - 1]);
      });
    }

    advance(currentStepId) {
      this.setBusy(false);
      const next = this.nextStepAfter(currentStepId);
      this.currentStepId = next;
      this.renderStep(next);
    }

    setBusy(isBusy) {
      this.root.classList.toggle("vq-busy", isBusy);
    }

    renderInlineError(form, msg) {
      let el = form.querySelector(".vq-form-error");
      if (!el) {
        el = document.createElement("div");
        el.className = "vq-form-error";
        form.appendChild(el);
      }
      el.textContent = msg;
    }
  }

  function mountAll() {
    document.querySelectorAll("[data-vora-quiz]").forEach((el) => {
      if (el.__voraQuizMounted) return;
      el.__voraQuizMounted = true;
      const mode = el.getAttribute("data-vora-quiz-mode") || "page";
      const prefillProductId = el.getAttribute("data-vora-quiz-product-id") || null;
      new VoraQuiz(el, { mode, prefillProductId });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }

  window.VoraQuiz = VoraQuiz;
  window.voraQuizMountAll = mountAll;
})();