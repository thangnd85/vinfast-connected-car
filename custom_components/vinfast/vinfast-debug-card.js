class VinFastDebugCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error('Bạn cần khai báo entity của cảm biến System Debug Raw Data');
    }
    this.config = config;
    this.activeTab = 'log'; 
    this.filterText = '';
    this._logData = [];
    this._rawJsonData = {};
    this._lastState = null;
    this._isFetching = false;
  }

  // HÀM FETCH FILE JSON TRỰC TIẾP TỪ THƯ MỤC WWW
  async fetchDataDirectly(vin) {
    if (this._isFetching) return;
    this._isFetching = true;
    
    try {
        // Tải file Changelog (Thêm Timestamp để chống Cache của trình duyệt)
        const resLog = await fetch(`/local/vinfast_changelog_${vin.toLowerCase()}.json?v=${new Date().getTime()}`);
        if (resLog.ok) {
            this._logData = await resLog.json();
        }

        // Tải file State lấy Raw JSON
        const resState = await fetch(`/local/vinfast_state_${vin.toLowerCase()}.json?v=${new Date().getTime()}`);
        if (resState.ok) {
            const stateData = await resState.json();
            if (stateData && stateData.last_data && stateData.last_data.api_debug_raw_json) {
                try {
                    this._rawJsonData = JSON.parse(stateData.last_data.api_debug_raw_json);
                } catch(e) {}
            }
        }
        
        // Cập nhật lại giao diện sau khi tải xong file
        this.renderBody();
    } catch (e) {
        console.error("VinFast Debug Card: Lỗi đọc file JSON", e);
    }
    
    this._isFetching = false;
  }

  set hass(hass) {
    this._hass = hass;
    const entityId = this.config.entity;
    const stateObj = hass.states[entityId];

    if (!stateObj) {
      this.innerHTML = `<ha-card><div style="padding: 20px; color: red;">Không tìm thấy thực thể: ${entityId}</div></ha-card>`;
      return;
    }

    // Trích xuất số VIN
    let vin = "unknown";
    const parts = entityId.split('_');
    if (parts.length > 1) {
        vin = parts[1]; 
    }

    if (!this.content) {
      this.initUI();
      this.content = true;
      this.fetchDataDirectly(vin);
    }

    // CHÚ Ý SỰ THAY ĐỔI Ở ĐÂY: 
    // Chúng ta KHÔNG dùng stateObj.state để gán cho tiêu đề nữa.
    // StateObj giờ chỉ đóng vai trò là "Cái chuông" báo hiệu xe vừa có dữ liệu mới.
    if (stateObj.state !== this._lastState) {
        this._lastState = stateObj.state;
        
        // Delay 500ms để đảm bảo Python đã ghi xong file JSON ra ổ cứng, tránh đọc hụt
        setTimeout(() => {
            this.fetchDataDirectly(vin);
        }, 500);
    }
  }

  initUI() {
    this.innerHTML = `
      <ha-card class="debug-card">
        <div class="debug-header">
          <div>
            <ha-icon icon="mdi:console-network" style="color:#10b981; margin-right:8px;"></ha-icon>
            VINFAST DEBUG CONSOLE
          </div>
          <div id="debug-status-text" class="debug-status">Đang tải dữ liệu...</div>
        </div>
        
        <div class="debug-toolbar">
          <input type="text" id="debug-search" class="debug-search" placeholder="🔍 Nhập mã code (VD: 34213) hoặc giá trị để lọc...">
          <div class="debug-tabs">
            <button id="btn-tab-log" class="debug-tab active">Changelog (Lịch sử)</button>
            <button id="btn-tab-raw" class="debug-tab">Raw JSON (Tất cả)</button>
          </div>
        </div>

        <div class="debug-body">
          <div id="view-log" class="debug-view"></div>
          <pre id="view-raw" class="debug-view" style="display: none;"></pre>
        </div>
      </ha-card>
    `;

    const style = document.createElement('style');
    style.textContent = `
      .debug-card { background: #0f172a; color: #e2e8f0; font-family: monospace; border-radius: 12px; overflow: hidden; box-shadow: inset 0 0 20px rgba(0,0,0,0.5); border: 1px solid #1e293b;}
      .debug-header { background: #1e293b; padding: 12px 16px; font-size: 14px; font-weight: bold; border-bottom: 1px solid #334155; display:flex; align-items:center; justify-content: space-between; letter-spacing: 1px; color:#10b981;}
      .debug-status { font-size: 11px; font-weight: normal; color: #94a3b8; text-transform: none; letter-spacing: 0;}
      
      .debug-toolbar { padding: 12px; background: #0f172a; border-bottom: 1px solid #1e293b; }
      .debug-search { width: 100%; padding: 10px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #38bdf8; font-family: monospace; font-size: 13px; outline: none; margin-bottom: 10px; transition: border 0.2s; box-sizing: border-box;}
      .debug-search:focus { border-color: #38bdf8; }
      
      .debug-tabs { display: flex; gap: 8px; }
      .debug-tab { background: #1e293b; border: 1px solid #334155; color: #94a3b8; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-family: monospace; font-size: 12px; font-weight: bold; flex: 1; transition: all 0.2s;}
      .debug-tab:hover { background: #334155; color: white;}
      .debug-tab.active { background: #38bdf8; color: #0f172a; border-color: #38bdf8;}
      
      /* Cho phép Copy Text */
      .debug-body { 
          padding: 12px; height: 400px; overflow-y: auto; 
          user-select: text !important; -webkit-user-select: text !important; cursor: text;
      }
      
      .debug-body::-webkit-scrollbar { width: 8px; }
      .debug-body::-webkit-scrollbar-track { background: #0f172a; }
      .debug-body::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
      .debug-body::-webkit-scrollbar-thumb:hover { background: #475569; }

      .log-item { padding: 8px 10px; border-bottom: 1px dashed #1e293b; font-size: 13px; line-height: 1.5; display: flex; justify-content: space-between; align-items: center;}
      .log-item:hover { background: rgba(255,255,255,0.03); border-radius: 6px;}
      .log-left { display: flex; flex-direction: column; }
      .log-time { color: #64748b; font-size: 11px; margin-bottom: 4px;}
      .log-code { color: #f43f5e; font-weight: bold; letter-spacing: 0.5px;}
      .log-right { background: #1e293b; padding: 4px 10px; border-radius: 20px; border: 1px solid #334155;}
      .log-val-old { color: #94a3b8; text-decoration: line-through; margin: 0 4px;}
      .log-arrow { color: #10b981; margin: 0 4px;}
      .log-val-new { color: #10b981; font-weight: bold; font-size: 14px;}

      #view-raw { margin: 0; font-size: 13px; color: #38bdf8; white-space: pre-wrap; word-wrap: break-word; }
    `;
    this.appendChild(style);

    this.querySelector('#btn-tab-log').addEventListener('click', (e) => {
      this.activeTab = 'log';
      e.target.classList.add('active');
      this.querySelector('#btn-tab-raw').classList.remove('active');
      this.querySelector('#view-log').style.display = 'block';
      this.querySelector('#view-raw').style.display = 'none';
      this.renderBody();
    });

    this.querySelector('#btn-tab-raw').addEventListener('click', (e) => {
      this.activeTab = 'raw';
      e.target.classList.add('active');
      this.querySelector('#btn-tab-log').classList.remove('active');
      this.querySelector('#view-log').style.display = 'none';
      this.querySelector('#view-raw').style.display = 'block';
      this.renderBody();
    });

    this.querySelector('#debug-search').addEventListener('input', (e) => {
      this.filterText = e.target.value.toLowerCase();
      this.renderBody();
    });
  }

  renderBody() {
    // TỰ ĐỘNG ĐỒNG BỘ THỜI GIAN TRÊN HEADER VỚI DỮ LIỆU JSON
    const headerTitle = this.querySelector('#debug-status-text');
    if (headerTitle) {
        let totalCodes = Object.keys(this._rawJsonData).length;
        let latestTimeStr = "";
        
        // Lấy chính xác thời gian của sự kiện mới nhất trong file JSON
        if (Array.isArray(this._logData) && this._logData.length > 0) {
            let fullTime = this._logData[0].time;
            latestTimeStr = fullTime.includes(' ') ? fullTime.split(' ')[1] : fullTime;
        }

        if (totalCodes > 0) {
            headerTitle.innerText = `Đã thu thập ${totalCodes} mã${latestTimeStr ? ' (Mới nhất: ' + latestTimeStr + ')' : ''}`;
        }
    }

    // 1. RENDER CHANGELOG
    if (this.activeTab === 'log') {
        const viewLog = this.querySelector('#view-log');
        
        if (!Array.isArray(this._logData) || this._logData.length === 0) {
            viewLog.innerHTML = `<div style="color:#64748b; text-align:center; margin-top:20px;">[ >_ Đang chờ dữ liệu Log... ]</div>`;
            return;
        }

        let html = '';
        this._logData.forEach(item => {
            const time = item.time || "";
            const code = item.code || "";
            const oldVal = item.old_value || "";
            const newVal = item.new_value || "";

            if (this.filterText) {
                const searchStr = `${time} ${code} ${oldVal} ${newVal}`.toLowerCase();
                if (!searchStr.includes(this.filterText)) return;
            }

            html += `
                <div class="log-item">
                    <div class="log-left">
                        <span class="log-time">🕒 ${time}</span>
                        <span class="log-code">${code}</span>
                    </div>
                    <div class="log-right">
                        <span class="log-val-old">${oldVal}</span> 
                        <span class="log-arrow">➔</span> 
                        <span class="log-val-new">${newVal}</span>
                    </div>
                </div>
            `;
        });

        if (html === '') html = `<div style="color:#64748b; text-align:center; margin-top:20px;">[ Không tìm thấy kết quả phù hợp ]</div>`;
        viewLog.innerHTML = html;
    }

    // 2. RENDER RAW JSON
    if (this.activeTab === 'raw') {
        const viewRaw = this.querySelector('#view-raw');
        let filteredJson = {};
        
        if (this.filterText) {
            for (let [key, value] of Object.entries(this._rawJsonData)) {
                if (key.toLowerCase().includes(this.filterText) || String(value).toLowerCase().includes(this.filterText)) {
                    filteredJson[key] = value;
                }
            }
        } else {
            filteredJson = this._rawJsonData;
        }
        viewRaw.textContent = JSON.stringify(filteredJson, null, 2);
    }
  }

  getCardSize() { return 8; }
}

customElements.define('vinfast-debug-card', VinFastDebugCard);