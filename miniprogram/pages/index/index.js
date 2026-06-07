const api = require('../../utils/api')

Page({
  data: {
    dreams: [],
    allDreams: [],
    page: 1,
    hasMore: true,
    loading: false,
    keyword: '',
    nickname: '',
    // 记录图片加载失败的 dream id，用于显示占位
    failedImages: {}
  },

  onLoad() {
    // 延迟数据加载到页面渲染完成后，避免 "Expected updated data but get first rendering data"
    wx.nextTick(() => {
      this.loadDreams()
      this.loadProfile()
    })
  },

  onShow() {
    // 进入前台时刷新昵称
    this.loadProfile()
    // 如果页面从其他页面返回且是第一页，刷新列表
    if (this.data.page === 1 && this.data.dreams.length > 0) {
      this.setData({ page: 1, dreams: [], allDreams: [], hasMore: true, failedImages: {} })
      this.loadDreams()
    }
  },

  onPullDownRefresh() {
    this.setData({ page: 1, dreams: [], allDreams: [], hasMore: true, failedImages: {} })
    this.loadDreams()
  },

  loadProfile() {
    api.getUserProfile().then(res => {
      this.setData({ nickname: res.user.nickname || '' })
    }).catch(() => {})
  },

  loadDreams() {
    if (!this.data.hasMore) return
    this.setData({ loading: true })

    api.getDreamList(1, this.data.keyword).then(res => {
      const all = (res.data || []).map(d => ({
        ...d,
        dream_tags: typeof d.dream_tags === 'string' ? JSON.parse(d.dream_tags || '[]') : (d.dream_tags || [])
      }))

      // 随机打乱展示
      const shuffled = this._shuffle([...all])

      this.setData({
        dreams: shuffled,
        allDreams: all,
        hasMore: false,
        loading: false
      })
      wx.stopPullDownRefresh && wx.stopPullDownRefresh()
    }).catch(err => {
      // 已经有 toast 提示，不再重复
      this.setData({ loading: false })
      wx.stopPullDownRefresh && wx.stopPullDownRefresh()
    })
  },

  _shuffle(arr) {
    const a = [...arr]
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      const t = a[i]; a[i] = a[j]; a[j] = t
    }
    return a
  },

  loadMore() {
    const reshuffled = this._shuffle([...this.data.allDreams])
    this.setData({ dreams: reshuffled })
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value })
  },

  doSearch() {
    this.setData({ page: 1, dreams: [], allDreams: [], hasMore: true, failedImages: {} })
    this.loadDreams()
  },

  // 图片加载失败时用占位色块
  onImageError(e) {
    const id = e.currentTarget.dataset.id
    if (!id) return
    const key = 'failedImages.' + id
    this.setData({ [key]: true })
  },

  onLike(e) {
    const id = e.currentTarget.dataset.id
    if (!id) return
    api.likeDream(id).then(res => {
      const dreams = this.data.dreams.map(d => {
        if (d.id === id) d.like_count = res.like_count
        return d
      })
      this.setData({ dreams })
    }).catch(() => {})
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id
    if (!id) return
    wx.navigateTo({ url: '/pages/detail/detail?id=' + id })
  }
})
