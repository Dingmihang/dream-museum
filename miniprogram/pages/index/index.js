const api = require('../../utils/api')

Page({
  data: {
    dreams: [],
    allDreams: [],  // store all dreams for shuffling
    page: 1,
    hasMore: true,
    loading: true,
    keyword: '',
    nickname: ''
  },

  onLoad() {
    this.loadDreams()
    this.loadProfile()
  },

  onShow() {
    this.loadProfile()
    if (this.data.page === 1 && this.data.dreams.length > 0) {
      this.setData({ page: 1, dreams: [], allDreams: [], hasMore: true })
      this.loadDreams()
    }
  },

  onPullDownRefresh() {
    this.setData({ page: 1, dreams: [], allDreams: [], hasMore: true })
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

    // Load all available pages for shuffling
    api.getDreamList(1, this.data.keyword).then(res => {
      const all = res.data.map(d => ({
        ...d,
        dream_tags: typeof d.dream_tags === 'string' ? JSON.parse(d.dream_tags || '[]') : (d.dream_tags || [])
      }))
      
      // Shuffle for variety
      const shuffled = this._shuffle([...all])
      
      this.setData({
        dreams: shuffled,
        allDreams: all,
        hasMore: false,  // single page is enough
        loading: false
      })
      wx.stopPullDownRefresh && wx.stopPullDownRefresh()
    }).catch(() => {
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
    // Reshuffle on load more
    const reshuffled = this._shuffle([...this.data.allDreams])
    this.setData({ dreams: reshuffled })
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value })
  },

  doSearch() {
    this.setData({ page: 1, dreams: [], allDreams: [], hasMore: true })
    this.loadDreams()
  },

  onLike(e) {
    const id = e.currentTarget.dataset.id
    api.likeDream(id).then(res => {
      const dreams = this.data.dreams.map(d => {
        if (d.id === id) d.like_count = res.like_count
        return d
      })
      this.setData({ dreams })
    })
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/detail/detail?id=' + e.currentTarget.dataset.id })
  }
})
