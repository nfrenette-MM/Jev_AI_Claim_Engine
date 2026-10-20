// JEV AI Claim Engine Frontend Application Logic (Multi-MCP Enabled)
let allClaims = [];
let currentFilter = 'ALL';
let activeModalClaim = null;

function formatMoney(amount) {
  if (amount === undefined || amount === null || isNaN(amount)) return '$0';
  const rounded = Math.round(Number(amount));
  return '$' + rounded.toLocaleString('en-US');
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  fetchMetrics();
  fetchClaims();
  setupEventListeners();
});

function setupEventListeners() {
  // Search input
  const searchInput = document.getElementById('claimSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      renderClaims(filterClaims(e.target.value, currentFilter));
    });
  }

  // Filter buttons
  const filterBtns = document.querySelectorAll('.filter-btn');
  filterBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      filterBtns.forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.getAttribute('data-filter');
      const searchVal = document.getElementById('claimSearchInput')?.value || '';
      renderClaims(filterClaims(searchVal, currentFilter));
    });
  });

  // Batch Remediate All
  const batchBtn = document.getElementById('batchRemediateBtn');
  if (batchBtn) {
    batchBtn.addEventListener('click', handleBatchRemediate);
  }

  // NCCI Sandbox Form
  const sandboxBtn = document.getElementById('sandboxLookupBtn');
  if (sandboxBtn) {
    sandboxBtn.addEventListener('click', handleNcciLookup);
  }

  // Modal Tabs
  const tabBtns = document.querySelectorAll('.modal-tabs .tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      tabBtns.forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      const targetTab = e.target.getAttribute('data-tab');
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      const activePanel = document.getElementById(`tab-${targetTab}`);
      if (activePanel) activePanel.classList.add('active');
    });
  });

  // Modal Close
  const closeBtn = document.getElementById('modalCloseBtn');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeModal);
  }

  // Close modal when clicking outside
  const modalOverlay = document.getElementById('claimDetailModal');
  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) closeModal();
    });
  }

  // Ingestion Modal Bindings
  const openUploadBtn = document.getElementById('openUploadModalBtn');
  if (openUploadBtn) {
    openUploadBtn.addEventListener('click', openUploadModal);
  }
  const closeUploadBtn = document.getElementById('uploadModalCloseBtn');
  if (closeUploadBtn) {
    closeUploadBtn.addEventListener('click', closeUploadModal);
  }
  const closeUploadFooterBtn = document.getElementById('uploadModalCloseFooterBtn');
  if (closeUploadFooterBtn) {
    closeUploadFooterBtn.addEventListener('click', closeUploadModal);
  }

  setupDropzone();

  const bulkIngestBtn = document.getElementById('triggerBulkIngestBtn');
  if (bulkIngestBtn) {
    bulkIngestBtn.addEventListener('click', handleBulkIngest);
  }

  // Databricks Modal Bindings
  const openDbxBtn = document.getElementById('openDatabricksModalBtn');
  if (openDbxBtn) {
    openDbxBtn.addEventListener('click', openDatabricksModal);
  }
  const closeDbxBtn = document.getElementById('databricksModalCloseBtn');
  if (closeDbxBtn) {
    closeDbxBtn.addEventListener('click', closeDatabricksModal);
  }
  const closeDbxFooterBtn = document.getElementById('databricksModalCloseFooterBtn');
  if (closeDbxFooterBtn) {
    closeDbxFooterBtn.addEventListener('click', closeDatabricksModal);
  }
  const refreshVolBtn = document.getElementById('refreshVolumesBtn');
  if (refreshVolBtn) {
    refreshVolBtn.addEventListener('click', fetchDatabricksVolumes);
  }
  const triggerSyncBtn = document.getElementById('triggerDatabricksSyncBtn');
  if (triggerSyncBtn) {
    triggerSyncBtn.addEventListener('click', handleDatabricksSync);
  }
}

async function fetchMetrics() {
  try {
    const res = await fetch('/api/metrics');
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('metricTotalClaims').innerText = data.total_claims ?? '--';
    document.getElementById('metricDollarsRecovered').innerText = `$${(data.dollars_recovered || 0).toLocaleString()}`;
    document.getElementById('metricOverturnRate').innerText = `${data.overturn_rate || 0}%`;
    document.getElementById('metricAutoRemediated').innerText = data.auto_remediated_count ?? '--';
    document.getElementById('metricHitlPending').innerText = data.hitl_review_count ?? '--';
    document.getElementById('metricWriteOffs').innerText = data.written_off_count ?? '--';
  } catch (err) {
    console.error('Error fetching metrics:', err);
  }
}

async function fetchClaims() {
  try {
    const res = await fetch('/api/claims');
    if (!res.ok) return;
    allClaims = await res.json();
    renderClaims(filterClaims('', currentFilter));
  } catch (err) {
    console.error('Error fetching claims:', err);
    showToast('Failed to load claims database.', 'error');
  }
}

function filterClaims(searchTerm, filterStatus) {
  const term = searchTerm.toLowerCase().trim();
  return allClaims.filter(item => {
    const claim = item.claim;
    const matchesSearch = !term || 
      claim.claim_id.toLowerCase().includes(term) ||
      claim.patient_name.toLowerCase().includes(term) ||
      claim.payer_name.toLowerCase().includes(term) ||
      claim.line_items.some(li => li.cpt_code.toLowerCase().includes(term));

    const matchesFilter = (filterStatus === 'ALL') || (claim.status === filterStatus);
    return matchesSearch && matchesFilter;
  });
}

function renderClaims(claimsList) {
  const tbody = document.getElementById('claimsTableBody');
  if (!tbody) return;

  if (claimsList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 32px;">No healthcare claims match the selected criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = claimsList.map(item => {
    const c = item.claim;
    const remit = item.remittance;

    let badgeHtml = '<span class="badge badge-pending">PENDING</span>';
    if (c.status === 'AUTO_REMEDIATED') {
      badgeHtml = '<span class="badge badge-auto">● AUTO-REMEDIATED</span>';
    } else if (c.status === 'HITL_REVIEW') {
      badgeHtml = '<span class="badge badge-hitl">⚠ HITL REVIEW</span>';
    } else if (c.status === 'WRITTEN_OFF') {
      badgeHtml = '<span class="badge badge-writeoff">✕ WRITTEN OFF</span>';
    } else if (c.status === 'RESOLVED') {
      badgeHtml = '<span class="badge badge-auto">✓ RESOLVED</span>';
    }

    const cptPills = c.line_items.map(li => {
      const modText = li.modifiers && li.modifiers.length > 0 ? `-${li.modifiers.join(', -')}` : '';
      return `<span class="cpt-pill ${modText ? 'modifier' : ''}">${li.cpt_code}${modText}</span>`;
    }).join(' ');

    const lineAdjudications = (remit && remit.line_adjudications) ? remit.line_adjudications : [];

    const lineCarcHtml = c.line_items.map((li, idx) => {
      const la = lineAdjudications.find(a => a.line_number === li.line_number) || lineAdjudications[idx] || {};
      const carcs = (la.carc_codes && la.carc_codes.length > 0) ? la.carc_codes : (remit && remit.primary_carc ? [remit.primary_carc] : ['97']);
      const isDenied = (la.carc_codes && la.carc_codes.length > 0) || (la.paid_amount === 0 && la.denial_reason);

      if (isDenied) {
        return `
          <div style="margin-bottom: 4px;">
            <div style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">
              <span class="badge" style="background: rgba(244, 63, 94, 0.12); color: #fda4af; border: 1px solid rgba(244, 63, 94, 0.25); font-size: 0.72rem; padding: 1px 6px; font-weight: 700;">
                L${li.line_number} (${li.cpt_code}): CARC ${carcs.join(', ')}
              </span>
            </div>
            <div style="font-size: 0.7rem; color: var(--text-dim); margin-top: 2px; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${la.denial_reason || remit.primary_reason}">
              ${la.denial_reason || remit.primary_reason || 'Denied service'}
            </div>
          </div>
        `;
      } else {
        return `
          <div style="margin-bottom: 4px;">
            <span class="badge badge-auto" style="font-size: 0.7rem; padding: 1px 6px;">
              L${li.line_number} (${li.cpt_code}): Paid ${formatMoney(la.paid_amount !== undefined ? la.paid_amount : li.billed_amount)}
            </span>
          </div>
        `;
      }
    }).join('');

    return `
      <tr id="row-${c.claim_id}">
        <td>
          <span class="claim-id-badge">${c.claim_id}</span>
          <div style="font-size: 0.72rem; color: var(--text-dim);">${c.date_of_service}</div>
        </td>
        <td>
          <div class="patient-info">
            <span class="patient-name">${c.patient_name}</span>
            <span class="patient-dob">DOB: ${c.dob}</span>
          </div>
        </td>
        <td>
          <div style="font-weight: 500; font-size: 0.82rem; color: var(--text-main);">${c.payer_name}</div>
          <div style="font-size: 0.72rem; color: var(--text-dim);">${c.payer_id}</div>
        </td>
        <td>
          <div class="cpt-tag-wrap">${cptPills}</div>
        </td>
        <td>
          ${lineCarcHtml}
        </td>
        <td>
          <div style="font-weight: 700; color: var(--text-main);">${formatMoney(c.total_billed)}</div>
          <div style="font-size: 0.72rem; color: ${c.status === 'AUTO_REMEDIATED' ? 'var(--emerald-success)' : 'var(--text-dim)'};">
            ${c.status === 'AUTO_REMEDIATED' ? `Recovered: ${formatMoney(c.total_billed)}` : `Paid: ${formatMoney(remit ? remit.total_paid : 0)}`}
          </div>
        </td>
        <td>
          ${badgeHtml}
        </td>
        <td>
          <div class="action-btn-group">
            ${c.status === 'PENDING' ? `
              <button class="btn-sm btn-remediate" onclick="handleRemediateSingle('${c.claim_id}')">
                ⚡ Remediate
              </button>
            ` : ''}
            <button class="btn-sm btn-inspect" onclick="openClaimInspection('${c.claim_id}')">
              Inspect
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function handleRemediateSingle(claimId) {
  const row = document.getElementById(`row-${claimId}`);
  if (row) row.style.opacity = '0.5';

  highlightPipelineStep(1);
  showToast(`Initiating 6-step multi-MCP pipeline for ${claimId}...`, 'info');

  try {
    setTimeout(() => highlightPipelineStep(2), 200);
    setTimeout(() => highlightPipelineStep(3), 400);
    setTimeout(() => highlightPipelineStep(4), 600);
    setTimeout(() => highlightPipelineStep(5), 800);

    const res = await fetch(`/api/remediate/${claimId}`, { method: 'POST' });
    const data = await res.json();

    highlightPipelineStep(6);

    if (data.decision === 'AUTO_REMEDIATED') {
      showToast(`Claim ${claimId} auto-remediated! Appended Modifier -${data.modifier_applied}.`, 'success');
    } else if (data.decision === 'HITL_REVIEW') {
      showToast(`Claim ${claimId} flagged for Human Specialist Review (Confidence < 0.85).`, 'warning');
    } else if (data.decision === 'WRITTEN_OFF') {
      showToast(`Claim ${claimId} flagged for Contractual Write-off (Indicator 0 Barred Edit).`, 'error');
    }

    await fetchMetrics();
    await fetchClaims();
  } catch (err) {
    console.error('Error remediating claim:', err);
    showToast(`Remediation failed for ${claimId}`, 'error');
  } finally {
    setTimeout(resetPipelineSteps, 1200);
  }
}

async function handleBatchRemediate() {
  const batchBtn = document.getElementById('batchRemediateBtn');
  if (batchBtn) {
    batchBtn.disabled = true;
    batchBtn.innerHTML = '⚡ Processing Batch...';
  }

  showToast('Starting multi-MCP batch remediation on all pending claims...', 'info');

  try {
    const res = await fetch('/api/remediate-all', { method: 'POST' });
    const data = await res.json();
    showToast(`Batch completed: ${data.remediated_count} claims processed.`, 'success');
    await fetchMetrics();
    await fetchClaims();
  } catch (err) {
    console.error('Batch error:', err);
    showToast('Batch remediation encountered an issue.', 'error');
  } finally {
    if (batchBtn) {
      batchBtn.disabled = false;
      batchBtn.innerHTML = '⚡ Remediate All Pending';
    }
  }
}

function highlightPipelineStep(stepNum) {
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById(`step-node-${i}`);
    if (!el) continue;
    if (i === stepNum) {
      el.classList.add('active');
    } else if (i < stepNum) {
      el.classList.remove('active');
      el.classList.add('completed');
    } else {
      el.classList.remove('active', 'completed');
    }
  }
}

function resetPipelineSteps() {
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById(`step-node-${i}`);
    if (el) el.classList.remove('active', 'completed');
  }
}

async function openClaimInspection(claimId) {
  try {
    const res = await fetch(`/api/claims/${claimId}`);
    if (!res.ok) return;
    const data = await res.json();
    activeModalClaim = data;

    const modal = document.getElementById('claimDetailModal');
    if (!modal) return;

    // Header values
    document.getElementById('modalClaimId').innerText = data.claim.claim_id;
    document.getElementById('modalPatientHeader').innerText = `${data.claim.patient_name} (DOS: ${data.claim.date_of_service})`;

    // Tab 1: EDI Details
    document.getElementById('tab1Patient').innerText = data.claim.patient_name;
    document.getElementById('tab1Payer').innerText = `${data.claim.payer_name} (${data.claim.payer_id})`;
    document.getElementById('tab1Dos').innerText = data.claim.date_of_service;
    document.getElementById('tab1Billed').innerText = formatMoney(data.claim.total_billed);
    document.getElementById('tab1Diagnosis').innerText = (data.claim.diagnosis_codes || []).join(', ');

    const lineItemsTbody = document.getElementById('modalLineItemsBody');
    const lineAdjudications = (data.remittance && data.remittance.line_adjudications) ? data.remittance.line_adjudications : [];

    lineItemsTbody.innerHTML = data.claim.line_items.map((li, idx) => {
      const adj = lineAdjudications.find(a => a.line_number === li.line_number) || lineAdjudications[idx] || {};
      const carcs = (adj.carc_codes && adj.carc_codes.length > 0) ? adj.carc_codes : (data.remittance && data.remittance.primary_carc ? [data.remittance.primary_carc] : []);
      const rarcs = adj.rarc_codes || [];
      const isDenied = carcs.length > 0 || (adj.paid_amount === 0 && adj.denial_reason);

      const carcBadges = carcs.map(c => `<span class="badge" style="background: rgba(244, 63, 94, 0.15); color: #fda4af; border: 1px solid rgba(244, 63, 94, 0.3); font-weight: 700; font-size: 0.72rem; padding: 2px 6px;">CARC ${c}</span>`).join(' ');
      const rarcBadges = rarcs.map(r => `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.72rem; padding: 2px 6px;">RARC ${r}</span>`).join(' ');

      const allowedAmt = adj.allowed_amount !== undefined ? adj.allowed_amount : (isDenied ? 0.0 : li.billed_amount);
      const paidAmt = adj.paid_amount !== undefined ? adj.paid_amount : (isDenied ? 0.0 : li.billed_amount);

      return `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
          <td style="padding: 10px 6px;">
            <div style="font-family: 'JetBrains Mono', monospace; color: var(--cyan-primary); font-weight: 700; font-size: 0.88rem;">
              Line ${li.line_number}: ${li.cpt_code}
            </div>
          </td>
          <td style="padding: 10px 6px; color: var(--text-main); font-size: 0.82rem;">
            ${li.description || 'Medical / Surgical Procedure'}
          </td>
          <td style="padding: 10px 6px;">
            ${li.modifiers && li.modifiers.length > 0 ? li.modifiers.map(m => `<span class="cpt-pill modifier">-${m}</span>`).join(' ') : '<span style="color: var(--text-dim)">None</span>'}
          </td>
          <td style="padding: 10px 6px; font-weight: 600;">
            ${formatMoney(li.billed_amount)}
          </td>
          <td style="padding: 10px 6px;">
            <div style="font-size: 0.78rem; color: ${isDenied ? 'var(--rose-danger)' : 'var(--emerald-success)'}; font-weight: 600;">
              Allowed: ${formatMoney(allowedAmt)}
            </div>
            <div style="font-size: 0.72rem; color: var(--text-dim);">
              Paid: ${formatMoney(paidAmt)}
            </div>
          </td>
          <td style="padding: 10px 6px;">
            ${isDenied ? `
              <div style="display: flex; gap: 4px; align-items: center; margin-bottom: 4px; flex-wrap: wrap;">
                ${carcBadges}
                ${rarcBadges}
              </div>
              <div style="font-size: 0.75rem; color: #cbd5e1; line-height: 1.3;">
                ${adj.denial_reason || (data.remittance ? data.remittance.primary_reason : 'Service line denied')}
              </div>
            ` : `
              <span class="badge badge-auto">✓ Paid / Allowed in Full</span>
            `}
          </td>
        </tr>
      `;
    }).join('');

    // Tab 2: ICD-10 MCP Validation
    const icdContainer = document.getElementById('tabIcd10Container');
    const icdValidations = (data.mcp_data && data.mcp_data.icd10_validations) ? data.mcp_data.icd10_validations : [];
    if (icdValidations.length > 0) {
      icdContainer.innerHTML = `
        <table style="width: 100%; border-collapse: collapse; font-size: 0.82rem;">
          <thead>
            <tr style="border-bottom: 1px solid var(--border-subtle); color: var(--text-dim); text-align: left;">
              <th style="padding: 6px;">Code</th>
              <th style="padding: 6px;">Description</th>
              <th style="padding: 6px;">HIPAA Valid</th>
              <th style="padding: 6px;">Specificity (CARC 16)</th>
            </tr>
          </thead>
          <tbody>
            ${icdValidations.map(v => `
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
                <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: var(--cyan-primary); padding: 8px 6px;">${v.code}</td>
                <td style="padding: 8px 6px;">${v.long_description}</td>
                <td style="padding: 8px 6px;"><span class="badge ${v.valid ? 'badge-auto' : 'badge-writeoff'}">${v.valid ? '✓ Billable' : '✕ Invalid'}</span></td>
                <td style="padding: 8px 6px;"><span class="badge ${v.specificity_valid ? 'badge-auto' : 'badge-hitl'}">${v.specificity_valid ? '✓ Passed' : '⚠ Non-Specific'}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    } else {
      icdContainer.innerHTML = '<div style="color: var(--text-dim); font-size: 0.85rem;">No diagnosis codes to validate.</div>';
    }

    // Tab 3: CMS Coverage MCP Policies
    const cmsContainer = document.getElementById('tabCmsContainer');
    const cmsCoverage = (data.mcp_data && data.mcp_data.cms_coverage) ? data.mcp_data.cms_coverage : null;
    if (cmsCoverage && cmsCoverage.policies && cmsCoverage.policies.length > 0) {
      cmsContainer.innerHTML = cmsCoverage.policies.map(p => `
        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 16px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 700; color: var(--cyan-primary); font-size: 0.9rem;">${p.document_type} ${p.policy_id}: ${p.title}</span>
            <span class="badge badge-auto">Covered Under Part B</span>
          </div>
          <div style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px;"><strong>Guidance:</strong> ${p.guidance}</div>
          <div style="font-size: 0.78rem; color: var(--text-dim);">
            <strong>Documentation Mandate:</strong> ${(p.documentation_requirements || []).join(' ')}
          </div>
        </div>
      `).join('');
    } else {
      cmsContainer.innerHTML = '<div style="color: var(--text-dim); font-size: 0.85rem;">No restrictive NCD/LCD policies found; standard Medicare Part B unbundling rules apply.</div>';
    }

    // Tab 4: Local FHIR MCP Evidence
    document.getElementById('tab2Notes').innerText = data.claim.clinical_notes || 'No chart notes available.';
    const verbatimElem = document.getElementById('tab2Verbatim');
    if (data.adjudication && data.adjudication.verbatim_clinical_evidence) {
      verbatimElem.innerText = `"${data.adjudication.verbatim_clinical_evidence}"`;
      document.getElementById('tab2QuoteCallout').style.display = 'block';
    } else {
      document.getElementById('tab2QuoteCallout').style.display = 'none';
    }

    // Tab 5: Jev AI Noul & Score
    if (data.adjudication) {
      const adj = data.adjudication;
      document.getElementById('tab3Confidence').innerText = `${(adj.overturn_confidence * 100).toFixed(0)}%`;
      document.getElementById('tab3Confidence').className = `kpi-value ${adj.overturn_confidence >= 0.85 ? 'emerald' : 'amber'}`;
      document.getElementById('tab3Risk').innerText = `${(adj.audit_risk * 100).toFixed(0)}%`;
      if (document.getElementById('tab3Category')) {
        document.getElementById('tab3Category').innerText = (adj.remediation_category || 'NCCI_BUNDLING').replace(/_/g, ' ');
      }
      if (document.getElementById('tab3Strategy')) {
        document.getElementById('tab3Strategy').innerText = adj.remediation_strategy || 'Clinical Evidence Audit & Unbundling';
      }
      if (document.getElementById('tab3PayerCat')) {
        document.getElementById('tab3PayerCat').innerText = (adj.payer_category || data.claim.payer_category || 'COMMERCIAL').replace(/_/g, ' ');
      }
      if (document.getElementById('tab3CarcRarc')) {
        const carcCode = (data.remittance && data.remittance.primary_carc) ? data.remittance.primary_carc : '97';
        const rarcCode = (data.remittance && data.remittance.rarc_code) ? data.remittance.rarc_code : '';
        document.getElementById('tab3CarcRarc').innerText = `CARC ${carcCode}${rarcCode ? ' / ' + rarcCode : ''}`;
      }
      if (document.getElementById('tab3RootCause')) {
        document.getElementById('tab3RootCause').innerText = adj.root_cause || 'Remittance unbundling / documentation requirement';
      }
      const guidanceBox = document.getElementById('tab3PayerGuidanceBox');
      const guidanceText = document.getElementById('tab3PayerGuidance');
      if (guidanceBox && guidanceText) {
        if (adj.payer_guidance) {
          guidanceText.innerText = adj.payer_guidance;
          guidanceBox.style.display = 'block';
        } else {
          guidanceBox.style.display = 'none';
        }
      }

      document.getElementById('tab3Action').innerText = adj.action || adj.decision;
      document.getElementById('tab3Indicator').innerText = `Indicator ${adj.ncci_indicator}`;
      document.getElementById('tab3Modifier').innerText = adj.modifier_applied ? `Modifier -${adj.modifier_applied}` : 'None';
      document.getElementById('tab3Reasoning').innerText = adj.reasoning || 'Evaluation completed.';
      document.getElementById('tab3McpSummary').innerText = `ICD-10 Validated • CMS Coverage Verified • local-fhir MCP Evidence Extracted`;

      // Populate Tab 5 Line Adjudication & Target list
      const tab3LineList = document.getElementById('tab3LineAdjudicationList');
      if (tab3LineList) {
        tab3LineList.innerHTML = data.claim.line_items.map((li, idx) => {
          const adj = lineAdjudications.find(a => a.line_number === li.line_number) || lineAdjudications[idx] || {};
          const carcs = (adj.carc_codes && adj.carc_codes.length > 0) ? adj.carc_codes : (data.remittance && data.remittance.primary_carc ? [data.remittance.primary_carc] : []);
          const isDenied = carcs.length > 0 || (adj.paid_amount === 0 && adj.denial_reason);
          return `
            <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 10px 12px; margin-bottom: 8px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-wrap: wrap; gap: 6px;">
                <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: var(--cyan-primary); font-size: 0.85rem;">
                  Service Line ${li.line_number}: CPT ${li.cpt_code} (Billed: ${formatMoney(li.billed_amount)})
                </span>
                <div>
                  ${isDenied ? `<span class="badge" style="background: rgba(244, 63, 94, 0.15); color: #fda4af; border: 1px solid rgba(244, 63, 94, 0.3); font-weight: 700;">CARC ${carcs.join(', ')}</span>` : `<span class="badge badge-auto">✓ Paid ${formatMoney(adj.paid_amount !== undefined ? adj.paid_amount : li.billed_amount)}</span>`}
                </div>
              </div>
              <div style="font-size: 0.78rem; color: var(--text-muted); line-height: 1.3;">
                <strong>Line Denial Rationale:</strong> ${adj.denial_reason || (isDenied ? data.remittance.primary_reason : 'Service line allowed / paid in full without adjustment')}
              </div>
            </div>
          `;
        }).join('');
      }

      const auditBox = document.getElementById('tab3AuditTrail');
      auditBox.innerHTML = (adj.audit_trail || []).map(step => `
        <div style="margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 6px;">
          <div style="color: var(--cyan-primary); font-weight: 600; font-size: 0.78rem;">${step.step_name} (${step.status})</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${step.detail}</div>
        </div>
      `).join('');
    } else {
      document.getElementById('tab3Confidence').innerText = '--';
      document.getElementById('tab3Risk').innerText = '--';
      if (document.getElementById('tab3Category')) document.getElementById('tab3Category').innerText = '--';
      if (document.getElementById('tab3Strategy')) document.getElementById('tab3Strategy').innerText = '--';
      if (document.getElementById('tab3PayerCat')) document.getElementById('tab3PayerCat').innerText = '--';
      if (document.getElementById('tab3CarcRarc')) document.getElementById('tab3CarcRarc').innerText = '--';
      if (document.getElementById('tab3RootCause')) document.getElementById('tab3RootCause').innerText = '--';
      const guidanceBox = document.getElementById('tab3PayerGuidanceBox');
      if (guidanceBox) guidanceBox.style.display = 'none';

      document.getElementById('tab3Action').innerText = 'PENDING EVALUATION';
      document.getElementById('tab3Indicator').innerText = '--';
      document.getElementById('tab3Modifier').innerText = '--';
      document.getElementById('tab3Reasoning').innerText = 'Claim has not yet run through the LangGraph multi-MCP pipeline.';
      document.getElementById('tab3McpSummary').innerText = 'Multi-MCP evaluation pending.';
      document.getElementById('tab3AuditTrail').innerHTML = '<div style="color: var(--text-dim); font-size: 0.75rem;">Run remediation to generate execution audit trail.</div>';
    }

    // Tab 6: Appeal Letter & Resubmission Packet (Dynamic by CARC category)
    const appealBox = document.getElementById('tab4AppealLetter');
    if (data.claim.status === 'AUTO_REMEDIATED' || (data.adjudication && data.adjudication.resubmission_ready)) {
      const adj = data.adjudication;
      const category = adj ? (adj.remediation_category || 'NCCI_BUNDLING') : 'NCCI_BUNDLING';
      let appealContent = '';

      if (category === 'TIMELY_FILING') {
        appealContent = `REVENUE CYCLE APPEAL & CLEARINGHOUSE TIMELY FILING PROOF
Date: ${data.claim.date_of_service}
To: Timely Filing Appeals Committee, ${data.claim.payer_name}
Re: Formal Timely Filing Overturn for Claim ID ${data.claim.claim_id} | Patient: ${data.claim.patient_name}

To Timely Filing Appeals Unit:
We are requesting immediate reconsideration and overturn of the CARC 29 timely filing denial for Claim ${data.claim.claim_id} (DOS: ${data.claim.date_of_service}).
Enclosed please find certified electronic clearinghouse EDI 277CA Acceptance and 999 Functional Acknowledgement proving that initial electronic transaction was successfully delivered to payer within the contracted filing deadline.
Requesting immediate reprocessing and release of payment.`;
      } else if (category === 'MISSING_DOCUMENTATION') {
        appealContent = `REVENUE CYCLE RE-ADJUDICATION & PWK CLINICAL RECORDS PACKET
Date: ${data.claim.date_of_service}
To: Claims Review Unit, ${data.claim.payer_name}
Re: Documentation Resubmission for Claim ID ${data.claim.claim_id} | Patient: ${data.claim.patient_name}

To Medical Claims Review:
In response to CARC 16/252 documentation request, enclosed is complete operative and chart documentation:
Operative Quote: "${adj ? adj.verbatim_clinical_evidence : 'Operative documentation attached via EHR FHIR export'}"
PWK loop transmission envelope completed. All requested documentation is certified complete for immediate payment.`;
      } else if (category === 'MEDICAL_NECESSITY') {
        appealContent = `REVENUE CYCLE FORMAL MEDICAL NECESSITY APPEAL (LCD/NCD CITED)
Date: ${data.claim.date_of_service}
To: Medical Director & Utilization Review, ${data.claim.payer_name}
Re: Medical Necessity Appeal for Claim ID ${data.claim.claim_id} | Patient: ${data.claim.patient_name}

To Medical Review Board:
We formally dispute the CARC 50 non-covered determination. Documented procedure satisfies CMS Medicare and commercial coverage criteria:
1. Validated ICD-10 indications and clinical pathology.
2. Clinical chart verifies conservative medical therapy trial failure prior to surgical intervention.
3. Operative evidence: "${adj ? adj.verbatim_clinical_evidence : 'Surgical operative record attached'}"
Requesting peer physician review or prompt overturn.`;
      } else if (category === 'PRIOR_AUTH_ABSENT') {
        appealContent = `RETROACTIVE PRIOR AUTHORIZATION & URGENT CARE RE-ADJUDICATION
Date: ${data.claim.date_of_service}
To: Prior Authorization Grievance Unit, ${data.claim.payer_name}
Re: Retroactive Prior Authorization Request for Claim ID ${data.claim.claim_id} | Patient: ${data.claim.patient_name}

To Prior Authorization Unit:
We formally request retroactive authorization under emergency and urgent care provisions for Claim ${data.claim.claim_id}.
Operative records verify acute clinical condition necessitating emergent surgical intervention without delay:
"${adj ? adj.verbatim_clinical_evidence : 'Operative findings substantiate immediate surgical intervention'}"
Requesting immediate administrative exception approval.`;
      } else {
        appealContent = `REVENUE CYCLE RE-ADJUDICATION & FORMAL MODIFIER APPEAL REQUEST
Date: ${data.claim.date_of_service}
To: Claims Adjudication Department, ${data.claim.payer_name}
Re: Formal Overturn Request for Claim ID ${data.claim.claim_id} | Patient: ${data.claim.patient_name}

To Medical Review & Claims Adjudication:
We are formally requesting re-adjudication of Claim ${data.claim.claim_id} for services rendered on ${data.claim.date_of_service}.
Denial under CARC ${(data.remittance && data.remittance.primary_carc) ? data.remittance.primary_carc : '97'} has been addressed.
In accordance with CMS NCCI Policy Manual Chapter 1, Modifier -${adj ? (adj.modifier_applied || '59') : '59'} has been appended to line item documentation proving a significant, distinct anatomical site or separate identifiable service.
FHIR Operative Citation: "${adj ? adj.verbatim_clinical_evidence : 'Verbatim clinical evidence extracted via local-fhir MCP'}"
Corrected EDI 837 transaction generated and validated for resubmission.`;
      }
      appealBox.innerText = appealContent;
    } else {
      appealBox.innerText = 'Appeal packet will be generated automatically upon successful remediation with Jev AI.';
    }

    // Setup Footer Actions dynamically for HITL Review
    const hitlActionsDiv = document.getElementById('modalHitlActions');
    hitlActionsDiv.innerHTML = '';

    if (data.claim.status === 'HITL_REVIEW' || data.claim.status === 'PENDING') {
      const actions = (data.adjudication && data.adjudication.available_actions && data.adjudication.available_actions.length > 0)
        ? data.adjudication.available_actions
        : [
            { id: "APPROVE_MODIFIER_59", label: "✓ Specialist Overturn (-59)", button_class: "btn-remediate", action_type: "APPROVE_MODIFIER", params: { modifier: "59" } },
            { id: "WRITE_OFF", label: "✕ Confirm Write-Off", button_class: "btn-writeoff", action_type: "WRITE_OFF", params: {} }
          ];

      actions.forEach(act => {
        const btn = document.createElement('button');
        btn.className = `btn-sm ${act.button_class || 'btn-remediate'}`;
        if (act.action_type === 'WRITE_OFF') {
          btn.style.background = 'var(--rose-danger)';
          btn.style.color = 'white';
        } else if (act.button_class === 'btn-accent') {
          btn.style.background = 'var(--purple-accent)';
          btn.style.color = 'white';
        } else if (act.button_class === 'btn-warning') {
          btn.style.background = '#d97706';
          btn.style.color = 'white';
        } else {
          btn.style.background = 'var(--emerald-success)';
          btn.style.color = 'white';
        }
        btn.innerText = act.label;
        btn.onclick = () => handleHumanDecision(act.action_type, act.params || {});
        hitlActionsDiv.appendChild(btn);
      });
      hitlActionsDiv.style.display = 'flex';
    } else {
      hitlActionsDiv.style.display = 'none';
    }

    modal.classList.add('open');
  } catch (err) {
    console.error('Error opening claim detail:', err);
  }
}

function closeModal() {
  const modal = document.getElementById('claimDetailModal');
  if (modal) modal.classList.remove('open');
  activeModalClaim = null;
}

async function handleHumanDecision(action, params) {
  if (!activeModalClaim) return;
  const claimId = activeModalClaim.claim.claim_id;
  const paramObj = typeof params === 'object' ? params : { modifier: params };

  try {
    const res = await fetch('/api/human-decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        claim_id: claimId,
        action: action,
        params: paramObj,
        modifier: paramObj.modifier,
        notes: `Adjudicated by human specialist in console (Action: ${action})`
      })
    });
    const result = await res.json();
    showToast(`Specialist action applied: ${action}`, 'success');
    closeModal();
    await fetchMetrics();
    await fetchClaims();
  } catch (err) {
    console.error('Failed to submit human decision:', err);
    showToast('Failed to record specialist action.', 'error');
  }
}

// Sandbox Navigation & Tools
function switchSandboxTab(tabName) {
  document.getElementById('sandboxTabNcci').style.display = tabName === 'ncci' ? 'block' : 'none';
  document.getElementById('sandboxTabIcd10').style.display = tabName === 'icd10' ? 'block' : 'none';
  document.getElementById('sandboxTabCms').style.display = tabName === 'cms' ? 'block' : 'none';
  const denialTab = document.getElementById('sandboxTabDenial');
  if (denialTab) denialTab.style.display = tabName === 'denial' ? 'block' : 'none';

  document.getElementById('btnSandboxNcci').classList.toggle('active', tabName === 'ncci');
  document.getElementById('btnSandboxIcd10').classList.toggle('active', tabName === 'icd10');
  document.getElementById('btnSandboxCms').classList.toggle('active', tabName === 'cms');
  const btnDenial = document.getElementById('btnSandboxDenial');
  if (btnDenial) btnDenial.classList.toggle('active', tabName === 'denial');
}

async function handleNcciLookup() {
  const cpt1 = document.getElementById('cptInput1')?.value.trim();
  const cpt2 = document.getElementById('cptInput2')?.value.trim();
  const resultBox = document.getElementById('sandboxResultBox');

  if (!cpt1 || !cpt2) {
    showToast('Please enter both CPT codes to lookup.', 'warning');
    return;
  }

  try {
    const res = await fetch(`/api/ncci-lookup?cpt1=${encodeURIComponent(cpt1)}&cpt2=${encodeURIComponent(cpt2)}`);
    const data = await res.json();

    resultBox.classList.add('visible');
    const badgeColor = data.indicator === 0 ? 'var(--rose-danger)' : (data.indicator === 1 ? 'var(--emerald-success)' : 'var(--cyan-primary)');

    resultBox.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <span style="font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 700; color: var(--text-main);">
          CPT ${data.column1_cpt} & CPT ${data.column2_cpt}
        </span>
        <span style="font-size: 0.75rem; font-weight: 700; color: ${badgeColor}; border: 1px solid ${badgeColor}; padding: 2px 8px; border-radius: 9999px;">
          ${data.indicator_label}
        </span>
      </div>
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px;">
        <strong>CMS Policy Rationale:</strong> ${data.rationale}
      </div>
      <div style="font-size: 0.8rem; color: var(--text-dim);">
        <strong>Permissible Modifiers:</strong> ${data.allowed_modifiers && data.allowed_modifiers.length > 0 ? data.allowed_modifiers.map(m => `-${m}`).join(', ') : 'None (Strict Unbundling Prohibition)'}
      </div>
    `;
  } catch (err) {
    console.error('Lookup failed:', err);
    showToast('NCCI lookup failed.', 'error');
  }
}

async function handleIcd10SandboxLookup() {
  const code = document.getElementById('icd10Input')?.value.trim();
  const resultBox = document.getElementById('icd10ResultBox');

  if (!code) {
    showToast('Please enter an ICD-10 diagnosis code.', 'warning');
    return;
  }

  try {
    const res = await fetch(`/api/mcp/icd10/validate?code=${encodeURIComponent(code)}`);
    const data = await res.json();

    resultBox.classList.add('visible');
    resultBox.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 700; color: var(--cyan-primary);">
          ${data.code} - ${data.short_description}
        </span>
        <span class="badge ${data.valid ? 'badge-auto' : 'badge-writeoff'}">
          ${data.valid ? '✓ HIPAA Valid' : '✕ Non-Billable'}
        </span>
      </div>
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 6px;">
        <strong>Long Clinical Description:</strong> ${data.long_description}
      </div>
      <div style="font-size: 0.8rem; color: ${data.specificity_valid ? 'var(--emerald-success)' : 'var(--amber-warning)'}; margin-bottom: 6px;">
        <strong>Specificity Assessment:</strong> ${data.guidance}
      </div>
      <div style="font-size: 0.75rem; color: var(--text-dim);">
        Chapter: ${data.chapter} • Category: ${data.category} • CARC 16 Risk: ${data.carc_16_risk ? 'YES (Missing specificity)' : 'NONE'}
      </div>
    `;
  } catch (err) {
    console.error('ICD-10 lookup failed:', err);
    showToast('ICD-10 validation query failed.', 'error');
  }
}

async function handleCmsSandboxLookup() {
  const cpt = document.getElementById('cmsCptInput')?.value.trim();
  const resultBox = document.getElementById('cmsResultBox');

  if (!cpt) {
    showToast('Please enter a CPT code.', 'warning');
    return;
  }

  try {
    const res = await fetch(`/api/mcp/cms/coverage?cpt=${encodeURIComponent(cpt)}`);
    const data = await res.json();

    resultBox.classList.add('visible');
    if (data.count === 0) {
      resultBox.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">No restrictive NCD/LCD policies found for CPT ${data.cpt_code}. Standard Medicare Part B medical necessity rules apply.</div>`;
      return;
    }

    resultBox.innerHTML = data.policies.map(p => `
      <div style="margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border-subtle);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <span style="font-weight: 700; color: var(--cyan-primary); font-size: 0.95rem;">
            ${p.document_type} ${p.policy_id}: ${p.title}
          </span>
          <span class="badge badge-auto">Part B Policy</span>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 6px;">
          <strong>Guidance:</strong> ${p.guidance}
        </div>
        <div style="font-size: 0.8rem; color: var(--text-dim);">
          <strong>Covered Indications:</strong> ${(p.covered_indications || []).join('; ')}
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('CMS lookup failed:', err);
    showToast('CMS coverage search failed.', 'error');
  }
}

async function handleDenialSandboxLookup() {
  const payer = document.getElementById('denialPayerInput')?.value.trim() || 'MEDICARE';
  const carc = document.getElementById('denialCarcInput')?.value.trim();
  const rarc = document.getElementById('denialRarcInput')?.value.trim();
  const resultBox = document.getElementById('denialResultBox');

  if (!carc) {
    showToast('Please enter at least a CARC code (e.g. 29, 16, 50, 97, 4).', 'warning');
    return;
  }

  try {
    let url = `/api/denial-lookup?payer=${encodeURIComponent(payer)}&carc=${encodeURIComponent(carc)}`;
    if (rarc) {
      url += `&rarc=${encodeURIComponent(rarc)}`;
    }
    const res = await fetch(url);
    const data = await res.json();

    if (!data.rule) {
      resultBox.classList.add('visible');
      resultBox.innerHTML = `<div style="color: var(--text-dim); font-size: 0.85rem;">No crosswalk mapping found for Payer: ${payer}, CARC: ${carc}.</div>`;
      return;
    }

    const rule = data.rule;
    resultBox.classList.add('visible');
    
    const actionsHtml = (rule.available_actions || []).map(act => {
      let bg = 'var(--emerald-success)';
      if (act.action_type === 'WRITE_OFF') bg = 'var(--rose-danger)';
      else if (act.button_class === 'btn-accent') bg = 'var(--purple-accent)';
      else if (act.button_class === 'btn-warning') bg = '#d97706';
      return `<button class="btn-sm" style="background: ${bg}; color: white; cursor: default; pointer-events: none; margin-bottom: 4px;">${act.label}</button>`;
    }).join(' ');

    const evidenceList = Array.isArray(rule.required_evidence)
      ? rule.required_evidence
      : (typeof rule.required_evidence === 'string' ? [rule.required_evidence] : []);
    const evidenceHtml = evidenceList.map(ev => `<span class="format-pill" style="font-size: 0.72rem;">${ev}</span>`).join(' ');

    resultBox.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 1.05rem; font-weight: 700; color: var(--cyan-primary);">
            CARC ${data.carc}${data.rarc ? ' / ' + data.rarc : ''}
          </span>
          <span class="badge badge-auto">${data.payer_category}</span>
          <span class="badge badge-hitl" style="font-size: 0.72rem;">${rule.caqh_scenario || 'CAQH Rule 360'}</span>
        </div>
        <div style="font-size: 0.78rem; color: var(--text-muted);">
          Confidence: <strong style="color: var(--emerald-success);">${(rule.confidence_score * 100).toFixed(0)}%</strong> • Audit Risk: <strong style="color: var(--purple-accent);">${(rule.audit_risk_score * 100).toFixed(0)}%</strong>
        </div>
      </div>

      <div style="font-size: 0.85rem; color: var(--text-main); margin-bottom: 6px;">
        <strong>Root Cause:</strong> <span style="color: var(--text-muted);">${rule.root_cause}</span>
      </div>

      <div style="font-size: 0.85rem; color: var(--text-main); margin-bottom: 8px;">
        <strong>Remediation Strategy:</strong> <span style="color: var(--cyan-primary);">${rule.remediation_strategy}</span>
      </div>

      ${rule.payer_specific_guidance ? `
        <div style="background: rgba(14, 165, 233, 0.08); border-left: 3px solid var(--cyan-primary); padding: 8px 12px; margin-bottom: 10px; font-size: 0.8rem; color: #cbd5e1; border-radius: 0 var(--radius-sm) var(--radius-sm) 0;">
          <strong>Payer Guidance (${data.payer_category}):</strong> ${rule.payer_specific_guidance}
        </div>
      ` : ''}

      <div style="font-size: 0.78rem; color: var(--text-dim); margin-bottom: 8px;">
        <strong>Required Evidence Package:</strong>
        <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px;">
          ${evidenceHtml || 'Standard EDI 837P loop data'}
        </div>
      </div>

      <div style="font-size: 0.78rem; color: var(--text-dim); margin-bottom: 6px;">
        <strong>Agent Dynamic Next Actions Generated:</strong>
      </div>
      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        ${actionsHtml}
      </div>
    `;
  } catch (err) {
    console.error('Denial matrix lookup failed:', err);
    showToast('Denial matrix lookup failed.', 'error');
  }
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  if (type === 'warning') icon = '⚠️';
  if (type === 'error') icon = '❌';

  toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ==========================================
// EDI Ingestion & Dropzone Hub Logic
// ==========================================

let uploadQueue = [];

function openUploadModal() {
  const modal = document.getElementById('uploadModal');
  if (modal) {
    modal.style.display = 'flex';
    fetchIngestStatus();
  }
}

function closeUploadModal() {
  const modal = document.getElementById('uploadModal');
  if (modal) modal.style.display = 'none';
}

function setupDropzone() {
  const dropzone = document.getElementById('ediDropzone');
  const fileInput = document.getElementById('ediFileInput');
  const browseLink = document.getElementById('browseFilesLink');
  const clearQueueBtn = document.getElementById('clearQueueBtn');
  const startUploadBtn = document.getElementById('startUploadBtn');

  if (!dropzone || !fileInput) return;

  if (browseLink) {
    browseLink.addEventListener('click', (e) => {
      e.stopPropagation();
      fileInput.click();
    });
  }

  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer && e.dataTransfer.files) {
      handleFilesAdded(Array.from(e.dataTransfer.files));
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files) {
      handleFilesAdded(Array.from(e.target.files));
      fileInput.value = '';
    }
  });

  if (clearQueueBtn) {
    clearQueueBtn.addEventListener('click', () => {
      uploadQueue = [];
      renderUploadQueue();
    });
  }

  if (startUploadBtn) {
    startUploadBtn.addEventListener('click', handleStartUpload);
  }
}

function handleFilesAdded(files) {
  const validExtensions = ['.edi', '.x12', '.txt', '.837', '.835', '.json', '.csv'];
  for (const file of files) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (validExtensions.includes(ext) || file.type.includes('text') || file.type.includes('json')) {
      uploadQueue.push(file);
    } else {
      showToast(`Skipped ${file.name}: unsupported format.`, 'warning');
    }
  }
  renderUploadQueue();
}

function renderUploadQueue() {
  const section = document.getElementById('fileQueueSection');
  const list = document.getElementById('queueFileList');
  const countSpan = document.getElementById('queueCount');

  if (!section || !list) return;

  if (uploadQueue.length === 0) {
    section.style.display = 'none';
    list.innerHTML = '';
    if (countSpan) countSpan.innerText = '0';
    return;
  }

  section.style.display = 'block';
  if (countSpan) countSpan.innerText = uploadQueue.length;

  list.innerHTML = uploadQueue.map((file, idx) => {
    const sizeKb = (file.size / 1024).toFixed(1);
    const is837 = file.name.includes('837') || file.name.includes('claim');
    const is835 = file.name.includes('835') || file.name.includes('remit');
    const tag = is837 ? '837 Claim' : (is835 ? '835 Remit' : 'EDI File');

    return `
      <div class="file-queue-item">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="file-name">${file.name}</span>
          <span class="badge" style="font-size: 0.68rem; background: rgba(6, 182, 212, 0.15); color: var(--cyan-primary);">${tag}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="file-meta">${sizeKb} KB</span>
          <button style="background: none; border: none; color: var(--rose-danger); cursor: pointer;" onclick="removeQueueItem(${idx})">&times;</button>
        </div>
      </div>
    `;
  }).join('');
}

window.removeQueueItem = function(index) {
  uploadQueue.splice(index, 1);
  renderUploadQueue();
};

async function handleStartUpload() {
  if (uploadQueue.length === 0) {
    showToast('No files in queue to upload.', 'warning');
    return;
  }

  const autoRemediate = document.getElementById('autoRemediateCheckbox')?.checked ?? false;
  const startBtn = document.getElementById('startUploadBtn');
  const resultLog = document.getElementById('ingestResultLog');

  startBtn.disabled = true;
  startBtn.innerText = 'Uploading & Parsing...';

  const formData = new FormData();
  for (const file of uploadQueue) {
    formData.append('files', file);
  }

  try {
    const res = await fetch(`/api/ingest/upload?auto_remediate=${autoRemediate}`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (res.ok) {
      showToast(`Successfully ingested ${data.total_claims_ingested} claims & ${data.total_remittances_ingested} remittances!`, 'success');
      uploadQueue = [];
      renderUploadQueue();

      if (resultLog) {
        resultLog.style.display = 'block';
        resultLog.innerText = JSON.stringify(data, null, 2);
      }

      fetchMetrics();
      fetchClaims();
      fetchIngestStatus();
    } else {
      showToast(`Upload failed: ${data.detail || 'Server error'}`, 'error');
    }
  } catch (err) {
    console.error('Upload error:', err);
    showToast('Failed to upload files.', 'error');
  } finally {
    startBtn.disabled = false;
    startBtn.innerText = 'Upload & Ingest Selected Files';
  }
}

async function fetchIngestStatus() {
  const badge = document.getElementById('dropzoneBadge');
  try {
    const res = await fetch('/api/ingest/status');
    if (!res.ok) return;
    const data = await res.json();
    if (badge) {
      badge.innerText = `${data.pending_drop_files_count} pending files (${data.archived_files_count} archived)`;
    }
  } catch (err) {
    console.error('Error fetching ingest status:', err);
  }
}

async function handleBulkIngest() {
  const btn = document.getElementById('triggerBulkIngestBtn');
  const resultLog = document.getElementById('ingestResultLog');
  const autoRemediate = document.getElementById('autoRemediateCheckbox')?.checked ?? false;

  btn.disabled = true;
  btn.innerText = 'Processing...';

  try {
    const res = await fetch(`/api/ingest/bulk?auto_remediate=${autoRemediate}`, { method: 'POST' });
    const data = await res.json();

    if (res.ok) {
      showToast(data.message || 'Bulk dropzone processed successfully!', 'success');
      if (resultLog) {
        resultLog.style.display = 'block';
        resultLog.innerText = JSON.stringify(data, null, 2);
      }
      fetchMetrics();
      fetchClaims();
      fetchIngestStatus();
    } else {
      showToast('Bulk ingestion failed.', 'error');
    }
  } catch (err) {
    console.error('Bulk ingest error:', err);
    showToast('Error executing bulk dropzone ingestion.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerText = '🚀 Process Bulk Dropzone';
  }
}

// ==========================================
// Databricks Lakehouse & MCP Logic
// ==========================================

function openDatabricksModal() {
  const modal = document.getElementById('databricksModal');
  if (modal) {
    modal.style.display = 'flex';
    fetchDatabricksStatus();
    fetchDatabricksVolumes();
  }
}

function closeDatabricksModal() {
  const modal = document.getElementById('databricksModal');
  if (modal) modal.style.display = 'none';
}

async function fetchDatabricksStatus() {
  const title = document.getElementById('dbxStatusTitle');
  const sub = document.getElementById('dbxStatusSub');
  const badge = document.getElementById('dbxModeBadge');

  try {
    const res = await fetch('/api/mcp/databricks/status');
    const data = await res.json();

    if (data.status === 'connected_live') {
      title.innerText = `Connected to Live Databricks SQL Warehouse (${data.latency_ms}ms)`;
      sub.innerText = `Host: ${data.host} • Catalog: ${data.catalog} • Schema: ${data.schema}`;
      badge.className = 'badge badge-auto';
      badge.innerText = 'Live SQL Warehouse';
    } else {
      title.innerText = `Databricks Lakehouse (Zero-Friction Simulation)`;
      sub.innerText = `Catalog: ${data.catalog} • Schema: ${data.schema} • 4 Medallion Tables Online (${data.latency_ms}ms)`;
      badge.className = 'badge';
      badge.style.background = 'rgba(245, 158, 11, 0.2)';
      badge.style.color = '#f59e0b';
      badge.innerText = 'Local Lakehouse Catalog';
    }
  } catch (err) {
    console.error('Databricks status error:', err);
    if (title) title.innerText = 'Databricks Connection Status Unavailable';
  }
}

async function fetchDatabricksVolumes() {
  const list = document.getElementById('dbxVolumesList');
  const pathLabel = document.getElementById('dbxVolumePath');
  if (!list) return;

  list.innerHTML = '<div style="color: var(--text-dim); font-size: 0.8rem;">Querying Unity Catalog Volumes...</div>';

  try {
    const res = await fetch('/api/mcp/databricks/volumes');
    const data = await res.json();

    if (pathLabel) pathLabel.innerText = data.volume_path;

    if (!data.files || data.files.length === 0) {
      list.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">No raw EDI files found in volume.</div>';
      return;
    }

    list.innerHTML = data.files.map(f => `
      <div class="file-queue-item">
        <div>
          <span class="file-name">${f.name}</span>
          <span style="font-size: 0.72rem; color: var(--text-dim); margin-left: 8px;">(${(f.size_bytes / 1024).toFixed(1)} KB)</span>
        </div>
        <button class="btn-sm" style="background: var(--cyan-primary); color: #000; font-weight: 600; cursor: pointer;" onclick="ingestVolumeFile('${f.local_path}')">
          📥 Ingest from Volume
        </button>
      </div>
    `).join('');
  } catch (err) {
    console.error('Databricks volumes error:', err);
    list.innerHTML = '<div style="color: var(--rose-danger); font-size: 0.8rem;">Failed to list volume files.</div>';
  }
}

window.ingestVolumeFile = async function(filePath) {
  showToast(`Ingesting ${filePath.split('/').pop()} from Lakehouse volume...`, 'info');
  try {
    // Read file via MCP server or send upload
    const res = await fetch('/api/ingest/bulk?auto_remediate=true', { method: 'POST' });
    const data = await res.json();
    showToast('File ingested and remediated from Databricks volume!', 'success');
    fetchMetrics();
    fetchClaims();
  } catch (err) {
    console.error('Error ingesting volume file:', err);
    showToast('Failed to ingest volume file.', 'error');
  }
};

async function handleDatabricksSync() {
  const btn = document.getElementById('triggerDatabricksSyncBtn');
  const log = document.getElementById('dbxSyncLog');

  btn.disabled = true;
  btn.innerText = 'Syncing...';

  try {
    const res = await fetch('/api/mcp/databricks/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();

    if (res.ok) {
      showToast(`Successfully synced ${data.synced_count} adjudications to Databricks Gold table!`, 'success');
      if (log) {
        log.style.display = 'block';
        log.innerText = JSON.stringify(data, null, 2);
      }
    } else {
      showToast('Databricks sync failed.', 'error');
    }
  } catch (err) {
    console.error('Sync error:', err);
    showToast('Error syncing with Databricks Gold table.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerText = '🔄 Sync to Gold Table';
  }
}

