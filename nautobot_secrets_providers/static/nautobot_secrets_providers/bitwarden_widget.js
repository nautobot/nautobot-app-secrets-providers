(function () {
    "use strict";

    const customFieldSelect = document.getElementById("id_custom_field_name");
    const secretIdInput = document.getElementById("id_secret_id");
    const secretFieldSelect = document.getElementById("id_secret_field");
    const searchBtn = document.getElementById("bw-search-items-btn");
    const searchAnchor = document.getElementById("bw-search-anchor");
    const searchPanel = document.getElementById("bw-search-panel");
    const searchQueryInput = document.getElementById("bw-search-query");
    const searchRunBtn = document.getElementById("bw-search-run-btn");
    const searchStatus = document.getElementById("bw-search-status");
    const searchResults = document.getElementById("bw-search-results");
    const customFieldStatus = document.getElementById("bw-custom-field-status");
    const descriptionInput = document.getElementById("id_description");

    let lastResolvedSecretName = "";
    let selectedSearchIndex = -1;

    if (!customFieldSelect || !secretIdInput || !secretFieldSelect || !searchBtn) {
        return;
    }

    const itemInfoUrl = searchBtn.getAttribute("data-item-info-url") || "";
    const searchUrl = searchBtn.getAttribute("data-search-url") || "";
    const originalSecretFieldOptions = Array.from(secretFieldSelect.options).map((opt) => ({
        value: opt.value,
        text: opt.text,
    }));

    const bitwardenApi = {
        requestJson(url, query) {
            if (!url) {
                return Promise.resolve({ success: false, error: "Bitwarden API endpoint is unavailable." });
            }
            const params = new URLSearchParams(query || {});
            const requestUrl = params.toString() ? `${url}?${params}` : url;
            return fetch(requestUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } }).then((r) => r.json());
        },
        getItemInfo(id) {
            return this.requestJson(itemInfoUrl, { secret_id: id });
        },
        searchItems(q) {
            return this.requestJson(searchUrl, { search: q });
        },
    };

    function findHelpElementFor(element) {
        const parent = element ? element.parentElement : null;
        if (!parent) {
            return null;
        }

        const selectors = [
            ".help-block", ".help-text", "small.form-text", "small.text-muted",
            "p.help-block", "div.help-block", ".field-help", "small.help-text",
        ];
        for (const selector of selectors) {
            const found = parent.querySelector(selector);
            if (found) {
                return found;
            }
        }

        let sibling = element.nextElementSibling;
        while (sibling) {
            if (["SMALL", "P", "DIV", "SPAN"].includes(sibling.tagName)) {
                return sibling;
            }
            sibling = sibling.nextElementSibling;
        }

        return null;
    }

    const secretHelp = findHelpElementFor(secretIdInput);

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function syncParametersJson() {
        const parametersInput = document.getElementById("id_parameters");
        if (!parametersInput) {
            return;
        }

        parametersInput.value = JSON.stringify(
            {
                secret_id: secretIdInput.value || "",
                secret_field: secretFieldSelect.value || "",
                custom_field_name: customFieldSelect.value || "",
            },
            null,
            4
        );
    }

    function showCustomFieldStatus(message, isError) {
        if (!customFieldStatus) {
            return;
        }

        customFieldStatus.textContent = message || "";
        customFieldStatus.className = isError ? "text-danger" : "text-muted";
        customFieldStatus.style.display = message ? "" : "none";
    }

    function clearSearchResults() {
        if (searchResults) {
            searchResults.innerHTML = "";
        }
        selectedSearchIndex = -1;
    }

    function getFieldContainer(element) {
        if (!element || !element.closest) {
            return null;
        }
        return element.closest(".form-group, .field-group, p, .controls, .json-field, .form-field") || element.parentElement;
    }

    function clearInlineValidation(targetElement) {
        const container = getFieldContainer(targetElement);
        if (!container) {
            return;
        }

        container.querySelectorAll(".bw-inline-validation").forEach((node) => node.remove());
        if (targetElement.classList) {
            targetElement.classList.remove("is-invalid");
        }
        targetElement.removeAttribute("aria-invalid");
    }

    function showInlineValidation(targetElement, message) {
        const container = getFieldContainer(targetElement);
        if (!container || !message) {
            return;
        }

        clearInlineValidation(targetElement);

        const validationNode = document.createElement("div");
        validationNode.className = "text-danger bw-inline-validation";
        validationNode.textContent = message;

        const helpElement = findHelpElementFor(targetElement);
        if (helpElement && helpElement.parentElement === container) {
            helpElement.insertAdjacentElement("afterend", validationNode);
        } else {
            targetElement.insertAdjacentElement("afterend", validationNode);
        }

        if (targetElement.classList) {
            targetElement.classList.add("is-invalid");
        }
        targetElement.setAttribute("aria-invalid", "true");
    }

    function hideDuplicateProviderError(message) {
        if (!message) {
            return;
        }

        const errorItems = Array.from(document.querySelectorAll(".errorlist li, .alert-danger li"));
        const matchingNode = errorItems.find((node) => (node.textContent || "").includes(message));
        if (!matchingNode) {
            return;
        }

        const errorList = matchingNode.closest("ul.errorlist");
        if (errorList && errorList.children.length === 1) {
            errorList.style.display = "none";
            const wrapper = errorList.parentElement;
            if (wrapper && wrapper.classList && wrapper.classList.contains("alert-danger")) {
                wrapper.style.display = "none";
            }
            return;
        }

        if (matchingNode instanceof HTMLElement) {
            matchingNode.style.display = "none";
        }
    }

    function getProviderValidationState() {
        const selectedField = (secretFieldSelect.value || "").trim();
        const customFieldName = (customFieldSelect.value || "").trim();

        if (selectedField === "custom" && !customFieldName) {
            return {
                field: customFieldSelect,
                text: "Custom field name is required if Secret field is set to 'Custom Field'.",
            };
        }

        if (customFieldName && selectedField !== "custom") {
            return {
                field: secretFieldSelect,
                text: "'Secret field' must be set to 'Custom Field' when 'Custom field name' is provided.",
            };
        }

        return null;
    }

    function syncProviderValidationDisplay() {
        clearInlineValidation(secretFieldSelect);
        clearInlineValidation(customFieldSelect);

        const state = getProviderValidationState();
        if (!state) {
            return;
        }

        showInlineValidation(state.field, state.text);
        hideDuplicateProviderError(state.text);
    }

    function autoFillDescription(itemName) {
        lastResolvedSecretName = itemName || lastResolvedSecretName;
        if (descriptionInput && itemName && !descriptionInput.value.trim()) {
            descriptionInput.value = itemName;
        }
    }

    function replaceIfMatchesName(itemName) {
        if (!descriptionInput || !itemName) {
            return;
        }
        if (descriptionInput.value.trim() === lastResolvedSecretName) {
            descriptionInput.value = itemName;
        }
        lastResolvedSecretName = itemName;
    }

    function restoreSelection(selectElement, targetValue) {
        const idx = Array.from(selectElement.options).findIndex((opt) => opt.value === targetValue);
        if (idx >= 0) {
            selectElement.selectedIndex = idx;
            return true;
        }
        return false;
    }

    function applySecretFieldFilter(allowedSecretFields) {
        const selectedValue = secretFieldSelect.value;
        const allowedMap = {};
        const fragment = document.createDocumentFragment();

        secretFieldSelect.innerHTML = "";

        if (Array.isArray(allowedSecretFields) && allowedSecretFields.length > 0) {
            allowedSecretFields.forEach((name) => {
                allowedMap[name] = true;
            });
        }

        originalSecretFieldOptions.forEach((optInfo) => {
            if (Array.isArray(allowedSecretFields) && allowedSecretFields.length > 0 && !allowedMap[optInfo.value]) {
                return;
            }

            const option = document.createElement("option");
            option.value = optInfo.value;
            option.text = optInfo.text;
            fragment.appendChild(option);
        });

        secretFieldSelect.appendChild(fragment);
        if (!restoreSelection(secretFieldSelect, selectedValue) && secretFieldSelect.options.length > 0) {
            secretFieldSelect.selectedIndex = 0;
        }
    }

    function updateCustomFieldChoices(fieldNames) {
        const selectedValue = (customFieldSelect.value || "").trim();
        const initialValue = (customFieldSelect.dataset.initialCustomField || "").trim();
        const preferredValue = selectedValue || initialValue;
        const uniqueNames = [];

        if (Array.isArray(fieldNames)) {
            fieldNames.forEach((name) => {
                const normalized = String(name || "").trim();
                if (!normalized || uniqueNames.includes(normalized)) {
                    return;
                }
                uniqueNames.push(normalized);
            });
        }

        // Preserve an existing configured value when metadata has not provided
        // any custom fields yet (for example, first render of an edit form).
        if (!uniqueNames.length && preferredValue) {
            uniqueNames.push(preferredValue);
        }

        customFieldSelect.innerHTML = "";

        const emptyOption = document.createElement("option");
        emptyOption.value = "";
        emptyOption.text = "---------";
        customFieldSelect.appendChild(emptyOption);

        uniqueNames.forEach((name) => {
            const option = document.createElement("option");
            option.value = name;
            option.text = name;
            customFieldSelect.appendChild(option);
        });

        if (!restoreSelection(customFieldSelect, preferredValue)) {
            customFieldSelect.value = "";
        }

        if (uniqueNames.length > 0) {
            showCustomFieldStatus("Custom field list initialized from the selected Bitwarden item.", false);
        } else {
            showCustomFieldStatus("", false);
        }
    }

    function setCustomFieldState(options) {
        const stateOptions = options || {};
        const preserveExistingSelection = Boolean(stateOptions.preserveExistingSelection);
        const isCustomSelected = secretFieldSelect.value === "custom";
        customFieldSelect.disabled = !isCustomSelected;

        if (!isCustomSelected) {
            if (!(preserveExistingSelection && customFieldSelect.value.trim())) {
                customFieldSelect.value = "";
            }
            showCustomFieldStatus("", false);
        } else if (!secretIdInput.value.trim()) {
            showCustomFieldStatus("Select a Bitwarden item UUID to initialize custom field names.", false);
        }

        syncParametersJson();
        syncProviderValidationDisplay();
    }

    function updateSecretHelp(name) {
        if (!secretHelp) {
            return;
        }

        const existingWrapper = secretHelp.querySelector(".bw-secret-wrapper");
        if (existingWrapper) {
            existingWrapper.remove();
        }

        if (!name) {
            return;
        }

        const wrapper = document.createElement("span");
        wrapper.className = "bw-secret-wrapper";
        wrapper.innerHTML = ` (<span class="text-muted">Secret: </span><span class="bw-secret-name">&#39;${escapeHtml(name)}&#39;</span>)`;
        secretHelp.appendChild(wrapper);
    }

    function applyItemInfo(data, currentId) {
        if (secretIdInput.value.trim() !== currentId) {
            return;
        }

        if (data && data.success) {
            updateSecretHelp(data.name || "");
            applySecretFieldFilter(data.allowed_secret_fields || []);
            updateCustomFieldChoices(data.fields || []);

            if (data.name) {
                if (!descriptionInput || !descriptionInput.value.trim()) {
                    autoFillDescription(data.name);
                } else {
                    replaceIfMatchesName(data.name);
                }
            }

            setCustomFieldState();
            return;
        }

        updateSecretHelp("");
        updateCustomFieldChoices([]);
        showCustomFieldStatus(data && data.error ? data.error : "Unable to initialize custom field names.", true);
    }

    function fetchAndUpdateName(currentId) {
        if (!currentId || !itemInfoUrl) {
            updateSecretHelp("");
            updateCustomFieldChoices([]);
            return Promise.resolve();
        }

        return bitwardenApi.getItemInfo(currentId)
            .then((data) => applyItemInfo(data, currentId))
            .catch(() => {
                updateSecretHelp("");
                updateCustomFieldChoices([]);
                showCustomFieldStatus("Unable to initialize custom field names from Bitwarden.", true);
            });
    }

    function setSearchStatus(message) {
        if (searchStatus) {
            searchStatus.textContent = message;
        }
    }

    function focusSearchResult(index) {
        const buttons = searchResults ? Array.from(searchResults.querySelectorAll(".bw-search-item")) : [];
        if (!buttons.length) {
            selectedSearchIndex = -1;
            return;
        }

        const clamped = Math.max(0, Math.min(index, buttons.length - 1));
        buttons.forEach((button) => button.classList.remove("is-selected"));
        buttons[clamped].classList.add("is-selected");
        buttons[clamped].focus();
        selectedSearchIndex = clamped;
    }

    function commitSearchSelection(button) {
        if (!button) {
            return;
        }

        const currentId = button.getAttribute("data-item-id") || "";
        const itemName = button.getAttribute("data-item-name") || "";

        secretIdInput.value = currentId;
        searchPanel.style.display = "none";
        clearSearchResults();
        setSearchStatus("Enter at least 2 characters to search.");
        syncParametersJson();

        if (itemName) {
            if (!descriptionInput || !descriptionInput.value.trim()) {
                autoFillDescription(itemName);
            } else {
                replaceIfMatchesName(itemName);
            }
        }

        fetchAndUpdateName(currentId);
    }

    function renderSearchResults(items) {
        clearSearchResults();

        if (!Array.isArray(items) || !items.length) {
            setSearchStatus("No matching Bitwarden items found.");
            return;
        }

        items.forEach((item, index) => {
            const button = document.createElement("button");
            const nameSpan = document.createElement("span");
            const idSpan = document.createElement("span");

            button.type = "button";
            button.className = "bw-search-item";
            button.setAttribute("data-item-id", item.id || "");
            button.setAttribute("data-item-name", item.name || "");

            nameSpan.className = "bw-search-item-name";
            nameSpan.textContent = item.name || "(unnamed item)";

            idSpan.className = "bw-search-item-id";
            idSpan.textContent = item.id || "";

            button.appendChild(nameSpan);
            button.appendChild(idSpan);

            button.addEventListener("click", () => commitSearchSelection(button));
            button.addEventListener("dblclick", () => commitSearchSelection(button));
            button.addEventListener("keydown", (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    commitSearchSelection(button);
                    return;
                }

                if (event.key === "ArrowDown") {
                    event.preventDefault();
                    focusSearchResult(index + 1);
                    return;
                }

                if (event.key === "ArrowUp") {
                    event.preventDefault();
                    focusSearchResult(index - 1);
                }
            });

            searchResults.appendChild(button);
        });

        focusSearchResult(0);
        setSearchStatus("Select an item to copy its UUID.");
    }

    function runSearchRequest() {
        const query = searchQueryInput ? searchQueryInput.value.trim() : "";

        clearSearchResults();
        if (!searchUrl || query.length < 2) {
            setSearchStatus("Enter at least 2 characters to search.");
            return;
        }

        setSearchStatus("Searching Bitwarden items...");
        bitwardenApi.searchItems(query)
            .then((data) => {
                if (data && data.success) {
                    renderSearchResults(data.items || []);
                    return;
                }
                setSearchStatus(data && data.error ? data.error : "Bitwarden item search failed.");
            })
            .catch((err) => setSearchStatus(`Request failed: ${err && err.message ? err.message : String(err)}`));
    }

    function toggleSearchPanel() {
        if (!searchPanel) {
            return;
        }

        if (!searchPanel.style.display || searchPanel.style.display === "none") {
            searchPanel.style.display = "block";
            if (searchQueryInput) {
                searchQueryInput.focus();
            }
            return;
        }

        searchPanel.style.display = "none";
        clearSearchResults();
        setSearchStatus("Enter at least 2 characters to search.");
    }

    function isSecretDetailView() {
        const path = window.location && window.location.pathname ? window.location.pathname : "";
        return /^\/extras\/secrets\/[0-9a-f-]{36}\/?$/i.test(path);
    }

    function applyReadonlyViewRestrictions() {
        if (searchBtn) {
            searchBtn.style.display = "none";
        }
        if (searchAnchor) {
            searchAnchor.style.display = "none";
        }
        if (searchRunBtn) {
            searchRunBtn.style.display = "none";
        }
        if (searchPanel) {
            searchPanel.style.display = "none";
        }
        clearSearchResults();
    }

    function mountSearchControls() {
        if (!searchAnchor || !searchPanel || !searchBtn) {
            return;
        }

        searchAnchor.style.display = "block";
        searchAnchor.style.width = "100%";
        searchAnchor.style.maxWidth = "100%";
        searchBtn.style.marginLeft = "0";
        searchBtn.style.verticalAlign = "middle";
        secretIdInput.insertAdjacentElement("afterend", searchAnchor);
    }

    customFieldSelect.addEventListener("change", () => {
        syncParametersJson();
        syncProviderValidationDisplay();
    });

    secretFieldSelect.addEventListener("change", () => setCustomFieldState());

    secretIdInput.addEventListener("input", () => {
        const currentId = secretIdInput.value.trim();
        syncParametersJson();

        if (!currentId) {
            updateSecretHelp("");
            applySecretFieldFilter([]);
            updateCustomFieldChoices([]);
            setCustomFieldState();
            return;
        }

        fetchAndUpdateName(currentId);
    });

    searchBtn.addEventListener("click", () => toggleSearchPanel());

    if (searchRunBtn) {
        searchRunBtn.addEventListener("click", () => runSearchRequest());
    }

    if (searchQueryInput) {
        searchQueryInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                runSearchRequest();
            }
        });
    }

    if (isSecretDetailView()) {
        applyReadonlyViewRestrictions();
    } else {
        mountSearchControls();
    }

    updateCustomFieldChoices([]);
    setCustomFieldState({ preserveExistingSelection: true });
    syncProviderValidationDisplay();

    if (secretIdInput.value.trim()) {
        fetchAndUpdateName(secretIdInput.value.trim());
    }
}());
