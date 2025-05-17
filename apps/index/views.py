from django.http import HttpResponse
from django.shortcuts import render

# index.html
def index(request):
    try:
        return HttpResponse("<h1>Hello, world. You're at the index page.")
    except Exception as e:
        content = "<h1>Sorry, there was an error.</h1><p>Error message: " + str(e) + "</p>"
        return HttpResponse(content)

# browse.html
def browse(request):
    # 统计各朝代类书比例
    return render(request, 'browse.html')

def jump(request):
    # in, out
    action = request.POST.get('action', '')


# bottom pages(static)

def about(request):
    return HttpResponse("<h1>About Us</h1><p>This is a sample about page.</p>")

def contact(request):
    return HttpResponse("<h1>Contact Us</h1><p>This is a sample contact page.</p>")

def faq(request):
   return HttpResponse("<h1>FAQ</h1><p>This is a sample FAQ page.</p>")

def services(request):
    return HttpResponse("<h1>Services</h1><p>This is a sample services page.</p>")

def policy(request):
    return HttpResponse("<h1>Privacy Policy</h1><p>This is a sample privacy policy page.</p>")

