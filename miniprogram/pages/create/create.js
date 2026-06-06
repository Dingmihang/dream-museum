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
    progressText: '正在解析梦境...',
    quota: { free_count: 0, credit_count: 0 }
  },

  onLoad() {
    this.loadQuota()
  },

  onShow() {
    this.loadQuota()
  },

  loadQuota() {
    api.getUserProfile().then(res => {
      this.setData({ quota: res.user })
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

    this.setData({ generating: true, progressText: '正在解析梦境...' })

    // 模拟进度更新
    const progressTimer = setInterval(() => {
      const texts = ['正在解析梦境...', 'AI 正在生成标题...', '正在绘制梦境画面...', '即将完成...']
      const idx = Math.floor(Math.random() * texts.length)
      this.setData({ progressText: texts[idx] })
    }, 2000)

    api.createDream(this.data.prompt, this.data.style, false).then(res => {
      clearInterval(progressTimer)
      if (res.code === 403) {
        this.setData({ generating: false, showAdModal: true })
        return
      }
      this.setData({
        generating: false,
        generated: true,
        result: res.dream,
        quota: res.quota
      })
    }).catch(err => {
      clearInterval(progressTimer)
      this.setData({ generating: false })
      wx.showToast({ title: '生成失败，请重试', icon: 'none' })
    })
  },

  publish() {
    if (!this.data.result) return
    api.publishDream(this.data.result.id).then(() => {
      wx.showToast({ title: '已发布到梦境大厅', icon: 'success' })
      // 切换到梦境大厅
      wx.switchTab({ url: '/pages/index/index' })
    })
  },

  regenerate() {
    this.setData({
      generated: false,
      generating: false,
      result: null
    })
  },

  watchAd() {
    this.setData({ showAdModal: false })
    // 微信激励视频广告
    wx.showModal({
      title: '观看广告',
      content: '完整观看广告后获得 1 次生成机会',
      success: (res) => {
        if (res.confirm) {
          api.adCallback().then(res => {
            this.setData({ quota: { ...this.data.quota, credit_count: res.credit_count } })
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
