django-jqgrid
=============
django-jqgrid aims to make integrating jqgrid in your django project as simple as
defining which models you want exposed, while supporting the more
advanced features.


Prerequisites
-------------
* [jQuery 2.1](http://www.jquery.com)
* [jqGrid 5.1](http://www.trirand.com/blog/?page_id=6)
* [Django 1.9](http://www.djangoproject.com)

Example
-------

1. First define your grid somewhere (e.g., grids.py). Only a model or queryset
   and a url are required.
```
	class ExampleGrid(JqGrid):
    	model = SomeFancyModel # could also be a queryset
    	fields = ['id', 'name', 'desc'] # optional 
    	url = reverse_lazy('your_app_name:grid_handler')
    	caption = 'My First Grid' # optional
    	colmodel_overrides = {    # optional
       		'id': { 'editable': False, 'width':10 },
   	 	}
```

2. Create views to handle requests.
```
	def grid_handler(request):
    	# handles pagination, sorting and searching
    	grid = ExampleGrid()
    	return HttpResponse(grid.get_json(request), content_type="application/json")

	def grid_config(request):
    	# build a config suitable to pass to jqgrid constructor   
    	grid = ExampleGrid()
    	return HttpResponse(grid.get_config(), content_type="application/json")
```

3. Define urls for those views.
```
	url(r'^examplegrid/$', grid_handler, name='grid_handler'),
	url(r'^examplegrid/cfg/$', grid_config, name='grid_config'),
```

4. Configure jgrid to use the defined urls.
```
    {% load static %}
    
    <table id="my_grid"></table>
    <div id="my_grid_nav"></div>

    # don't forget to include jQuery first
    <link rel="stylesheet" href="{% static 'jqgrid/css/ui.jqgrid-bootstrap.css' %}">
    <script src="{% static 'jqgrid/js/jquery.jqGrid.js' %}"></script>
    <script src="{% static 'jqgrid/js/i18n/grid.locale-en.js' %}"></script>

    <script>
        $.ajax({
            method: 'GET',
            url: "{% url 'your_app_name:grid_config' %}",
            success: function (data) {
                $("#my_grid")
                        .jqGrid(data)
                        .navGrid('#my_grid_nav',
                                {add: false, edit: false, del: false, view: true},
                                {}, // edit options
                                {}, // add options
                                {}, // del options
                                {multipleSearch: true, closeOnEscape: true}, // search options
                                {jqModal: false, closeOnEscape: true} // view options
                        )
            },
            error: function (data) {
                alert("An error occurred!");
                console.log(data);
            },
        })
    </script>
```
