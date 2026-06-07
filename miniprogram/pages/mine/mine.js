const api = require('../../utils/api')

Page({
  data: {
    user: { free_count: 0, credit_count: 0, daily_free: 3, nickname: '梦行者', avatar: '' },
    tab: 'dreams',
    dreams: [],
    favs: [],
    dreamCount: 0,
    editName: '',
    showNameEdit: false
  },

  onShow() {
    this.loadProfile()
    this.loadDreams()
  },

  loadProfile() {
    api.getUserProfile().then(res => {
      const u = res.user || {}
      this.setData({ 
        user: {
          free_count: u.free_count || 0,
          credit_count: u.credit_count || 0,
          daily_free: u.daily_free || 3,
          nickname: u.nickname || '梦行者',
          avatar: u.avatar || ''
        },
        editName: u.nickname || ''
      })
    }).catch(() => {})
  },

  loadDreams() {
    api.getUserDreams(1).then(res => {
      const dreams = (res.data || []).map(d => ({
        ...d,
        dream_tags: typeof d.dream_tags === 'string' ? JSON.parse(d.dream_tags || '[]') : (d.dream_tags || [])
      }))
      this.setData({ dreams, dreamCount: res.total || dreams.length })
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
        this.setData({ favs: (res.data || []).map(d => ({
          ...d,
          dream_tags: typeof d.dream_tags === 'string' ? JSON.parse(d.dream_tags || '[]') : (d.dream_tags || [])
        })) })
      }).catch(() => {})
    }
  },

  // 图片加载失败处理
  onImageError(e) {
    const id = e.currentTarget.dataset.id
    if (!id) return
    const key = 'imgFailed_' + id
    this.setData({ [key]: true })
  },

  // 头像选择
  onChooseAvatar(e) {
    const avatarUrl = e.detail.avatarUrl
    this.setData({ 'user.avatar': avatarUrl })
    api.updateProfile('', avatarUrl).then(() => {
      wx.showToast({ title: '头像已更新', icon: 'success' })
    }).catch(() => {})
  },

  // 昵称修改
  onNameInput(e) {
    this.setData({ editName: e.detail.value })
  },

  saveNickname() {
    const name = (this.data.editName || '').trim()
    if (!name) return
    if (name !== this.data.user.nickname) {
      api.updateProfile(name, '').then(res => {
        this.setData({ 
          'user.nickname': res.user.nickname,
          editName: res.user.nickname,
          showNameEdit: false
        })
        wx.showToast({ title: '昵称已更新', icon: 'success' })
      }).catch(() => {})
    } else {
      this.setData({ showNameEdit: false })
    }
  },

  closeNameEdit() {
    this.setData({ showNameEdit: false })
  },

  watchAd() {
    wx.showModal({
      title: '观看广告',
      content: '观看广告获得 1 次生成机会',
      success: (res) => {
        if (res.confirm) {
          api.adCallback().then(res => {
            wx.showToast({ title: '获得1次机会', icon: 'success' })
            this.loadProfile()
          }).catch(() => {})
        }
      }
    })
  },

  deleteDream(e) {
    wx.showModal({
      title: '删除梦境',
      content: '确定删除吗？',
      success: (res) => {
        if (res.confirm) {
          api.deleteDream(e.currentTarget.dataset.id).then(() => {
            wx.showToast({ title: '已删除', icon: 'success' })
            this.loadDreams()
          }).catch(() => {})
        }
      }
    })
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id
    if (!id) return
    wx.navigateTo({ url: '/pages/detail/detail?id=' + id })
  },

  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          const app = getApp()
          app.logout()
        }
      }
    })
  }
})
