const api = require('../../utils/api')

Page({
  data: {
    user: { free_count: 0, credit_count: 0, daily_free: 1, nickname: '梦行者' },
    tab: 'dreams',
    dreams: [],
    favs: []
  },

  onShow() {
    this.loadProfile()
    this.loadDreams()
  },

  loadProfile() {
    api.getUserProfile().then(res => {
      this.setData({ user: res.user })
    }).catch(() => {})
  },

  loadDreams() {
    api.getUserDreams(1).then(res => {
      const dreams = (res.data || []).map(d => ({
        ...d,
        dream_tags: typeof d.dream_tags === 'string' ? JSON.parse(d.dream_tags || '[]') : (d.dream_tags || [])
      }))
      this.setData({ dreams })
    }).catch(() => {})
    api.getUserFavorites(1).then(res => {
      const favs = (res.data || []).map(d => ({
        ...d,
        dream_tags: typeof d.dream_tags === 'string' ? JSON.parse(d.dream_tags || '[]') : (d.dream_tags || [])
      }))
      this.setData({ favs })
    }).catch(() => {})
  },

  switchTab(e) {
    this.setData({ tab: e.currentTarget.dataset.tab })
    if (e.currentTarget.dataset.tab === 'favs') {
      api.getUserFavorites(1).then(res => {
        this.setData({ favs: res.data || [] })
      })
    }
  },

  watchAd() {
    wx.showModal({
      title: '观看广告',
      content: '完整观看广告获得 1 次生成机会',
      success: (res) => {
        if (res.confirm) {
          api.adCallback().then(res => {
            wx.showToast({ title: '获得1次机会', icon: 'success' })
            this.loadProfile()
          })
        }
      }
    })
  },

  deleteDream(e) {
    const id = e.currentTarget.dataset.id
    wx.showModal({
      title: '删除梦境',
      content: '确定删除这个梦境吗？',
      success: (res) => {
        if (res.confirm) {
          api.deleteDream(id).then(() => {
            wx.showToast({ title: '已删除', icon: 'success' })
            this.loadDreams()
          })
        }
      }
    })
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/detail/detail?id=' + e.currentTarget.dataset.id })
  }
})
