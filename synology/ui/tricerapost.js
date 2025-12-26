Ext.ns("SYNO.PKG.TriceraPost");

SYNO.PKG.TriceraPost.getBaseUrl = function() {
  return "/tricerapost";
};

SYNO.PKG.TriceraPost.applyStyles = function() {
  if (document.getElementById("tricerapost-dsm-css")) {
    return;
  }
  var css = [
    ".tricera-shell{background:#f2f4f6;}",
    ".tricera-header{display:flex;align-items:center;gap:12px;margin-bottom:12px;}",
    ".tricera-header img{width:36px;height:36px;border-radius:8px;}",
    ".tricera-title{font-size:20px;font-weight:600;color:#1f2a37;}",
    ".tricera-subtitle{color:#6b7280;font-size:12px;}",
    ".tricera-status{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;box-shadow:0 6px 16px rgba(15,23,42,0.06);}",
    ".tricera-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:12px;}",
    ".tricera-metric{background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px;}",
    ".tricera-metric span{display:block;color:#6b7280;font-size:12px;margin-bottom:6px;}",
    ".tricera-metric strong{font-size:18px;color:#111827;}",
    ".tricera-status-note{color:#6b7280;font-size:12px;margin-top:10px;}",
    ".tricera-toolbar .x-toolbar{background:transparent;border:none;}",
    ".tricera-tabs .x-tab-panel-header{background:#f2f4f6;border:none;}",
    ".tricera-form .x-form-item-label{color:#374151;font-weight:600;}",
    ".tricera-form .x-form-text{border-radius:8px;}",
    ".tricera-mask .x-mask-loading{border-radius:10px;}"
  ].join("");
  Ext.util.CSS.createStyleSheet(css, "tricerapost-dsm-css");
};

Ext.define("SYNO.PKG.TriceraPost.Instance", {
  extend: "SYNO.SDS.AppInstance",
  appWindowName: "SYNO.PKG.TriceraPost.MainWindow",
  constructor: function(config) {
    this.callParent(arguments);
  }
});

Ext.define("SYNO.PKG.TriceraPost.StatusPanel", {
  extend: "Ext.Panel",
  constructor: function(config) {
    SYNO.PKG.TriceraPost.applyStyles();
    this.tpl = new Ext.XTemplate(
      "<div class=\"tricera-status\">",
      "  <div class=\"tricera-header\">",
      "    <img src=\"/webman/3rdparty/tricerapost/images/TriceraPost_64.png\" alt=\"TriceraPost\" />",
      "    <div>",
      "      <div class=\"tricera-title\">TriceraPost</div>",
      "      <div class=\"tricera-subtitle\">Local Usenet indexer</div>",
      "    </div>",
      "  </div>",
      "  <div class=\"tricera-metrics\">",
      "    <div class=\"tricera-metric\"><span>Groups scanned</span><strong>{groups_scanned}</strong></div>",
      "    <div class=\"tricera-metric\"><span>Posts scanned</span><strong>{posts_scanned}</strong></div>",
      "    <div class=\"tricera-metric\"><span>Sets found</span><strong>{sets_found}</strong></div>",
      "    <div class=\"tricera-metric\"><span>Sets rejected</span><strong>{sets_rejected}</strong></div>",
      "    <div class=\"tricera-metric\"><span>NZBs found</span><strong>{nzbs_found}</strong></div>",
      "    <div class=\"tricera-metric\"><span>NZBs generated</span><strong>{nzbs_generated}</strong></div>",
      "  </div>",
      "  <div class=\"tricera-status-note\" id=\"tricera-status-note\">Last updated: {updated_at}</div>",
      "</div>"
    );

    config = Ext.apply(
      {
        border: false,
        autoScroll: true,
        bodyStyle: "padding:16px;",
        cls: "tricera-shell tricera-toolbar",
        tbar: [
          {
            xtype: "syno_button",
            text: "Refresh",
            scope: this,
            handler: this.refreshStatus
      },
      {
        xtype: "syno_button",
        text: "Save all NZBs",
        scope: this,
        handler: this.saveAllNzbs
      }
    ]
      },
      config
    );

    this.callParent([config]);
    this.on("afterrender", this.refreshStatus, this);
  },

  refreshStatus: function() {
    Ext.Ajax.request({
      url: SYNO.PKG.TriceraPost.getBaseUrl() + "/api/status",
      method: "GET",
      scope: this,
      success: function(resp) {
        var data = {};
        try {
          data = Ext.decode(resp.responseText);
        } catch (err) {
          data = {};
        }
        data.updated_at = new Date().toLocaleString();
        this.update(this.tpl.apply(data));
      },
      failure: function() {
        this.update(this.tpl.apply({
          groups_scanned: "-",
          posts_scanned: "-",
          sets_found: "-",
          sets_rejected: "-",
          nzbs_found: "-",
          nzbs_generated: "-",
          updated_at: "Failed to fetch status"
        }));
      }
    });
  }
  ,
  saveAllNzbs: function() {
    Ext.Ajax.request({
      url: SYNO.PKG.TriceraPost.getBaseUrl() + "/api/nzb/save_all",
      method: "POST",
      scope: this,
      success: function(resp) {
        var data = {};
        try {
          data = Ext.decode(resp.responseText);
        } catch (err) {
          data = { saved: 0 };
        }
        this.refreshStatus();
        this.getEl().mask("Saved " + (data.saved || 0) + " NZBs.", "x-mask-loading tricera-mask");
        Ext.defer(function() {
          this.getEl().unmask();
        }, 1200, this);
      },
      failure: function() {
        this.getEl().mask("Save failed.", "x-mask-loading tricera-mask");
        Ext.defer(function() {
          this.getEl().unmask();
        }, 1200, this);
      }
    });
  }
});

Ext.define("SYNO.PKG.TriceraPost.SettingsPanel", {
  extend: "Ext.Panel",
  constructor: function(config) {
    SYNO.PKG.TriceraPost.applyStyles();
    this.form = new Ext.form.FormPanel({
      border: false,
      bodyStyle: "padding:16px;",
      labelWidth: 160,
      cls: "tricera-form",
      defaults: { anchor: "100%" },
      items: [
        { xtype: "textfield", fieldLabel: "NNTP host", name: "NNTP_HOST" },
        { xtype: "numberfield", fieldLabel: "NNTP port", name: "NNTP_PORT", minValue: 1, maxValue: 65535 },
        { xtype: "checkbox", fieldLabel: "Use SSL", name: "NNTP_SSL" },
        { xtype: "textfield", fieldLabel: "NNTP username", name: "NNTP_USER" },
        { xtype: "textfield", inputType: "password", fieldLabel: "NNTP password", name: "NNTP_PASS" },
        { xtype: "displayfield", fieldLabel: "Password status", name: "NNTP_PASS_STATUS", value: "Unknown" },
        { xtype: "checkbox", fieldLabel: "Clear stored password", name: "CLEAR_PASS" },
        { xtype: "numberfield", fieldLabel: "NNTP lookback", name: "NNTP_LOOKBACK", minValue: 1 },
        { xtype: "textfield", fieldLabel: "Groups override", name: "NNTP_GROUPS" },
        { xtype: "checkbox", fieldLabel: "Save NZBs to disk", name: "TRICERAPOST_SAVE_NZBS" },
        { xtype: "textfield", fieldLabel: "NZB output directory", name: "TRICERAPOST_NZB_DIR" },
        { xtype: "displayfield", fieldLabel: "Save status", name: "SAVE_STATUS", value: "" }
      ],
      buttons: [
        {
          xtype: "syno_button",
          text: "Save settings",
          btnStyle: "blue",
          scope: this,
          handler: this.saveSettings
        },
        {
          xtype: "syno_button",
          text: "Reload",
          scope: this,
          handler: this.loadSettings
        },
        {
          xtype: "syno_button",
          text: "Clear database",
          scope: this,
          handler: this.clearDatabase
        }
      ]
    });

    config = Ext.apply(
      {
        border: false,
        layout: "fit",
        items: [this.form]
      },
      config
    );

    this.callParent([config]);
    this.on("afterrender", this.loadSettings, this);
  },

  loadSettings: function() {
    var form = this.form.getForm();
    Ext.Ajax.request({
      url: SYNO.PKG.TriceraPost.getBaseUrl() + "/api/settings",
      method: "GET",
      scope: this,
      success: function(resp) {
        var data = Ext.decode(resp.responseText);
        form.setValues({
          NNTP_HOST: data.NNTP_HOST || "",
          NNTP_PORT: data.NNTP_PORT || "",
          NNTP_SSL: Boolean(data.NNTP_SSL),
          NNTP_USER: data.NNTP_USER || "",
          NNTP_LOOKBACK: data.NNTP_LOOKBACK || "",
          NNTP_GROUPS: data.NNTP_GROUPS || "",
          TRICERAPOST_SAVE_NZBS: data.TRICERAPOST_SAVE_NZBS !== false,
          TRICERAPOST_NZB_DIR: data.TRICERAPOST_NZB_DIR || "",
          NNTP_PASS_STATUS: data.NNTP_PASS_SET ? "Password stored" : "No password stored",
          SAVE_STATUS: ""
        });
        form.findField("NNTP_PASS").setValue("");
        form.findField("CLEAR_PASS").setValue(false);
      },
      failure: function(resp) {
        form.findField("SAVE_STATUS").setValue("Failed to load settings.");
      }
    });
  },

  saveSettings: function() {
    var form = this.form.getForm();
    var values = form.getValues();
    var payload = {
      NNTP_HOST: values.NNTP_HOST || "",
      NNTP_PORT: values.NNTP_PORT || "",
      NNTP_SSL: form.findField("NNTP_SSL").getValue(),
      NNTP_USER: values.NNTP_USER || "",
      NNTP_LOOKBACK: values.NNTP_LOOKBACK || "",
      NNTP_GROUPS: values.NNTP_GROUPS || "",
      TRICERAPOST_SAVE_NZBS: form.findField("TRICERAPOST_SAVE_NZBS").getValue(),
      TRICERAPOST_NZB_DIR: values.TRICERAPOST_NZB_DIR || "",
      clear_password: form.findField("CLEAR_PASS").getValue()
    };
    if (values.NNTP_PASS) {
      payload.NNTP_PASS = values.NNTP_PASS;
    }

    form.findField("SAVE_STATUS").setValue("Saving...");
    Ext.Ajax.request({
      url: SYNO.PKG.TriceraPost.getBaseUrl() + "/api/settings",
      method: "POST",
      headers: { "Content-Type": "application/json" },
      jsonData: payload,
      scope: this,
      success: function() {
        form.findField("SAVE_STATUS").setValue("Settings saved.");
        this.loadSettings();
      },
      failure: function(resp) {
        form.findField("SAVE_STATUS").setValue("Save failed.");
      }
    });
  }
  ,
  clearDatabase: function() {
    Ext.Msg.confirm(
      "Clear database",
      "Clear all SQLite data and reset scans? This cannot be undone.",
      function(btn) {
        if (btn !== "yes") return;
        Ext.Ajax.request({
          url: SYNO.PKG.TriceraPost.getBaseUrl() + "/api/admin/clear_db",
          method: "POST",
          headers: { "Content-Type": "application/json" },
          jsonData: { confirm: true },
          scope: this,
          success: function() {
            this.form.getForm().findField("SAVE_STATUS").setValue("Database cleared.");
          },
          failure: function() {
            this.form.getForm().findField("SAVE_STATUS").setValue("Clear failed.");
          }
        });
      },
      this
    );
  }
});

Ext.define("SYNO.PKG.TriceraPost.MainWindow", {
  extend: "SYNO.SDS.AppWindow",
  constructor: function(config) {
    var statusPanel = new SYNO.PKG.TriceraPost.StatusPanel({ title: "Status" });
    var settingsPanel = new SYNO.PKG.TriceraPost.SettingsPanel({ title: "Settings" });

    config = Ext.apply(
      {
        title: "TriceraPost",
        width: 980,
        height: 680,
        layout: "fit",
        cls: "tricera-shell",
        icon: "/webman/3rdparty/tricerapost/images/TriceraPost_24.png",
        items: [
          new Ext.TabPanel({
            activeTab: 0,
            border: false,
            cls: "tricera-tabs",
            items: [statusPanel, settingsPanel]
          })
        ]
      },
      config
    );

    this.callParent([config]);
  }
});
