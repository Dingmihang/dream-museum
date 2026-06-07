const api = require('../../utils/api')

Page({
  data: {
    prompt: '',
    style: '梦核',
    styles: ['梦核', '怪核', '童年梦境', '恐怖梦境', '治愈梦境', '赛博梦境'],
    generating: false,
    generated: false,
    result: null,
    showAdModal: false,
    progressText: '正在感知梦境...',
    progressPct: 0,
    quota: { free_count: 0, credit_count: 0, daily_free: 3 },
    genFailed: false,
    resultImgFailed: false
  },

  _isPageActive: true,
  _timers: [],

  onLoad() {
    this._isPageActive = true
    this.loadQuota()
  },

  onUnload() {
    this._isPageActive = false
    this._clearTimers()
  },

  onShow() {
    this._isPageActive = true
    this.loadQuota()
  },

  onHide() {
    this._isPageActive = false
  },

  _clearTimers() {
    this._timers.forEach(clearTimeout)
    this._timers = []
  },

  loadQuota() {
    api.getUserProfile().then(res => {
      if (!this._isPageActive) return
      const u = res.user || {}
      this.setData({
        quota: {
          free_count: u.free_count || 0,
          credit_count: u.credit_count || 0,
          daily_free: u.daily_free || 3
        }
      })
    }).catch(() => {})
  },

  onInput(e) {
    this.setData({ prompt: e.detail.value })
  },

  pickStyle(e) {
    this.setData({ style: e.currentTarget.dataset.style })
  },

  generate() {
    if (!this.data.prompt.trim() || this.data.generating) return

    this._clearTimers()
    this.setData({ generating: true, genFailed: false, resultImgFailed: false, progressText: '正在感知梦境...', progressPct: 10 })

    const phases = [
      { text: 'AI 正在解析文字...', pct: 35, delay: 1500 },
      { text: '正在编织画面...', pct: 60, delay: 3000 },
      { text: '即将完成...', pct: 85, delay: 5000 },
    ]

    phases.forEach(p => {
      const t = setTimeout(() => {
        if (this._isPageActive && this.data.generating) {
          this.setData({ progressText: p.text, progressPct: p.pct })
        }
      }, p.delay)
      this._timers.push(t)
    })

    api.createDream(this.data.prompt, this.data.style, false).then(res => {
      this._clearTimers()
      if (!this._isPageActive) return

      this.setData({ progressPct: 100 })
      setTimeout(() => {
        if (!this._isPageActive) return
        if (res.code === 403) {
          this.setData({ generating: false, showAdModal: true, progressPct: 0 })
          return
        }
        this.setData({
          generating: false,
          generated: true,
          result: res.dream,
          quota: res.quota || this.data.quota,
          progressPct: 0
        })
      }, 300)
    }).catch(err => {
      this._clearTimers()
      if (!this._isPageActive) return
      this.setData({ generating: false, genFailed: true, progressPct: 0 })
    })
  },

  // 生成结果图片加载失败
  onResultImageError() {
    this.setData({ resultImgFailed: true })
  },

  publish() {
    if (!this.data.result || !this.data.result.id) {
      wx.showToast({ title: '请先成功生成梦境', icon: 'none' })
      return
    }
    api.publishDream(this.data.result.id).then(() => {
      wx.showToast({ title: '已发布到梦境大厅', icon: 'success' })
      setTimeout(() => {
        wx.switchTab({ url: '/pages/index/index' })
      }, 800)
    }).catch(() => {
      wx.showToast({ title: '发布失败，请重试', icon: 'none' })
    })
  },

  regenerate() {
    this.setData({
      generated: false,
      generating: false,
      result: null,
      genFailed: false,
      resultImgFailed: false
    })
  },

  watchAd() {
    this.setData({ showAdModal: false })
    wx.showModal({
      title: '观看广告',
      content: '完整观看广告后获得 1 次生成机会',
      success: (res) => {
        if (res.confirm) {
          api.adCallback().then(res => {
            if (!this._isPageActive) return
            this.setData({ quota: { ...this.data.quota, credit_count: res.credit_count || this.data.quota.credit_count + 1 } })
            wx.showToast({ title: '获得1次生成机会', icon: 'success' })
            this.generate()
          }).catch(() => {
            wx.showToast({ title: '广告加载失败', icon: 'none' })
          })
        }
      }
    })
  },

  closeAdModal() {
    this.setData({ showAdModal: false })
  }
})
