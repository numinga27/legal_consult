html_template = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body { 
    font-family: 'DejaVu Sans', 'Arial', sans-serif; 
    font-size: 12pt; 
    margin: 40px;
    color: #1a1a2e;
}
h1 { 
    color: #1a1a2e; 
    font-size: 18pt; 
    text-align: center; 
    margin-bottom: 30px;
}
.header { 
    text-align: right; 
    margin-bottom: 30px;
}
.content { 
    line-height: 1.8;
}
.footer { 
    margin-top: 50px; 
    text-align: right;
}
.document-title { 
    font-size: 20pt; 
    font-weight: bold; 
    text-align: center; 
    margin: 30px 0;
}
</style>
</head>
<body>
<div class="header">
    <p><strong>Дата:</strong> {{ current_date }}</p>
    <p><strong>ФИО:</strong> {{ full_name }}</p>
    <p><strong>Адрес:</strong> {{ address }}</p>
    <p><strong>Телефон:</strong> {{ phone }}</p>
    <p><strong>Email:</strong> {{ email }}</p>
</div>

<div class="document-title">ЮРИДИЧЕСКАЯ КОНСУЛЬТАЦИЯ</div>

<div class="content">
    <h3>{{ conclusion_title }}</h3>
    <p>{{ conclusion_full }}</p>
</div>

<div class="footer">
    <p>_________________________</p>
    <p><strong>Подпись:</strong> {{ full_name }}</p>
</div>
</body>
</html>
"""