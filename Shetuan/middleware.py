class AdminFrameMiddleware:
    """SimpleUI 的后台页面使用同源 iframe，其他页面保持 DENY。"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info.startswith('/admin/'):
            response['X-Frame-Options'] = 'SAMEORIGIN'
        return response
