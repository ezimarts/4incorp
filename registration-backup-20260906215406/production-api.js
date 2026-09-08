(() => {
  "use strict";

  const config = window.FOURINCORP_CONFIG || {};
  const apiBase = String(config.apiBaseUrl || "").replace(/\/$/, "");
  if (!apiBase) {
    console.info("4incorp production API is not configured; demo handlers remain available.");
    return;
  }

  const tokenKey = "4incorpIdToken";

  async function request(path, options = {}) {
    const token = sessionStorage.getItem(tokenKey);
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {})
      }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || `Request failed (${response.status})`);
    return data;
  }

  function formMessage(form, message, type) {
    const target = form.querySelector(".form-message");
    if (!target) return;
    target.textContent = message;
    target.className = `form-message ${type}`;
  }

  function replaceForm(id, handler) {
    const original = document.getElementById(id);
    if (!original) return null;
    const form = original.cloneNode(true);
    original.replaceWith(form);
    form.addEventListener("submit", handler);
    return form;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    })[character]);
  }

  function openClientDashboard(email) {
    document.querySelectorAll(".workspace").forEach(workspace => workspace.classList.remove("active"));
    document.getElementById("userWorkspace")?.classList.add("active");
    const label = document.getElementById("loggedInUserEmail");
    if (label) label.textContent = email;
    const main = document.querySelector("main");
    const header = document.querySelector(".site-header");
    const footer = document.querySelector("footer");
    if (main) main.style.display = "none";
    if (header) header.style.display = "none";
    if (footer) footer.style.display = "none";
    loadApplications();
  }

  async function loadApplications() {
    if (!sessionStorage.getItem(tokenKey)) return;
    try {
      const result = await request("/applications");
      const tbody = document.querySelector("#userWorkspace .demo-table tbody");
      if (!tbody) return;
      const applications = result.applications || [];
      tbody.innerHTML = applications.length ? applications.map(application => `
        <tr>
          <td>${escapeHtml(application.reference)}</td>
          <td>${escapeHtml(application.preferred_name)}</td>
          <td>${escapeHtml(application.formation_state)}</td>
          <td><span class="tiny-status">${escapeHtml(application.status)}</span></td>
          <td><button class="small-btn" type="button" onclick="window.fourincorpUploadDocument('${escapeHtml(application.reference)}')">Upload document</button></td>
        </tr>`).join("") : '<tr><td colspan="5">No applications have been submitted yet.</td></tr>';
    } catch (error) {
      console.error("Could not load applications", error);
    }
  }

  async function uploadDocument(reference) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf,.png,.jpg,.jpeg,.doc,.docx";
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const result = await request(`/applications/${encodeURIComponent(reference)}/documents`, {
          method: "POST",
          body: JSON.stringify({ file_name: file.name, content_type: file.type || "application/octet-stream" })
        });
        const uploadData = new FormData();
        Object.entries(result.upload.fields || {}).forEach(([key, value]) => uploadData.append(key, value));
        uploadData.append("file", file);
        const uploadResponse = await fetch(result.upload.url, { method: "POST", body: uploadData });
        if (!uploadResponse.ok) throw new Error(`Document upload failed (${uploadResponse.status})`);
        window.alert("Document uploaded successfully.");
      } catch (error) {
        window.alert(error.message);
      }
    }, { once: true });
    input.click();
  }

  replaceForm("registerForm", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const values = Object.fromEntries(new FormData(form).entries());
    if (values.password !== values.confirmPassword) {
      formMessage(form, "Passwords do not match.", "error");
      return;
    }
    try {
      await request("/auth/register", { method: "POST", body: JSON.stringify(values) });
      const code = window.prompt("Enter the confirmation code sent to your email:");
      if (code) {
        await request("/auth/confirm", {
          method: "POST",
          body: JSON.stringify({ email: values.email, code: code.trim() })
        });
        formMessage(form, "Client account confirmed. You can now sign in.", "success");
      } else {
        formMessage(form, "Account created. Confirm the email code before signing in.", "success");
      }
    } catch (error) {
      formMessage(form, error.message, "error");
    }
  });

  replaceForm("userLoginForm", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const values = Object.fromEntries(new FormData(form).entries());
    try {
      const result = await request("/auth/login", { method: "POST", body: JSON.stringify(values) });
      sessionStorage.setItem(tokenKey, result.id_token);
      formMessage(form, "Login successful. Opening client dashboard…", "success");
      openClientDashboard(String(values.email || ""));
    } catch (error) {
      formMessage(form, error.message, "error");
    }
  });

  const applicationForm = replaceForm("applicationForm", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const values = Object.fromEntries(new FormData(form).entries());
    delete values.accountPassword;
    delete values.confirmPassword;
    delete values.password;
    try {
      const submissionPath = sessionStorage.getItem(tokenKey) ? "/applications" : "/guest/applications";
      const result = await request(submissionPath, { method: "POST", body: JSON.stringify(values) });
      formMessage(form, `Application submitted. Order ${result.order_id}; reference ${result.reference}.`, "success");
      await loadApplications();
    } catch (error) {
      formMessage(form, error.message, "error");
    }
  });

  if (applicationForm && typeof window.updateReview === "function") {
    applicationForm.addEventListener("input", window.updateReview);
    applicationForm.addEventListener("change", window.updateReview);
  }

  if (typeof window.initEyeButtons === "function") window.initEyeButtons();
  window.fourincorpUploadDocument = uploadDocument;
  window.fourincorpApi = { request, loadApplications, uploadDocument };
})();
