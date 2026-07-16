import streamlit as st
import calendar
from datetime import date, datetime

def render_schedule_html(year, month, schedule_data):
    _, last_day = calendar.monthrange(year, month)
    
    # CSS Styles
    css = """
    <style>
    .schedule-container {
        overflow-x: auto;
        white-space: nowrap;
        padding-bottom: 10px;
    }
    .schedule-table {
        border-collapse: collapse;
        font-size: 12px;
        font-family: "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
    }
    .schedule-table th, .schedule-table td {
        border: 1px solid #ddd;
        text-align: center;
        vertical-align: top;
        padding: 5px;
    }
    .schedule-table th {
        background-color: #f0f0f0;
        font-weight: normal;
    }
    
    /* Dynamic Width Classes */
    .day-col-active {
        min-width: 60px;
        background-color: #fff;
    }
    .day-col-empty {
        width: 25px;
        max-width: 25px;
        background-color: #fafafa;
        color: #ccc;
        font-size: 10px;
    }
    
    /* Weekday Colors */
    .sat { color: blue; }
    .sun { color: red; }
    
    /* Button/Link Style */
    .venue-link {
        display: block;
        margin: 2px 0;
        padding: 4px 2px;
        background-color: #eee;
        color: #333;
        text-decoration: none;
        border-radius: 3px;
        font-size: 11px;
        cursor: pointer;
    }
    .venue-link:hover {
        background-color: #ddd;
    }
    .venue-link.active {
        background-color: #ffcc00; /* Highlight selected */
        font-weight: bold;
    }
    </style>
    """
    
    html = css + '<div class="schedule-container"><table class="schedule-table">'
    
    # Header Row (Date)
    html += '<tr>'
    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        weekday = current_date.weekday()
        weekday_str = ["月", "火", "水", "木", "金", "土", "日"][weekday]
        
        has_race = current_date in schedule_data
        css_class = "day-col-active" if has_race else "day-col-empty"
        
        # Color class
        color_class = ""
        if weekday == 5: color_class = "sat"
        elif weekday == 6: color_class = "sun"
        
        # Make date clickable (Select ALL venues)
        date_url = f"?date={current_date}&venue=ALL"
        header_content = f'<a href="{date_url}" target="_self" style="text-decoration:none; color:inherit; display:block; width:100%; height:100%;">{day}<br>{weekday_str}</a>'
        
        html += f'<th class="{css_class} {color_class}">{header_content}</th>'
    html += '</tr>'
    
    # Data Row (Venues)
    html += '<tr>'
    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        has_race = current_date in schedule_data
        css_class = "day-col-active" if has_race else "day-col-empty"
        
        cell_content = ""
        if has_race:
            venues = schedule_data[current_date]
            for venue in venues:
                # Check if selected
                is_selected = False
                if st.session_state.get('selected_date_str'):
                    try:
                        sel_date = datetime.strptime(st.session_state['selected_date_str'], "%Y-%m-%d").date()
                        is_selected = (sel_date == current_date and st.session_state.get('selected_venue') == venue)
                    except:
                        pass
                
                active_class = "active" if is_selected else ""
                
                # Link with query params
                url = f"?date={current_date}&venue={venue}"
                cell_content += f'<a href="{url}" target="_self" class="venue-link {active_class}">{venue}</a>'
            
        html += f'<td class="{css_class}">{cell_content}</td>'
    html += '</tr>'
    
    html += '</table></div>'
    return html
