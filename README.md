# Novel Chapter Tracker

Modern web application for tracking and managing novel chapters across Fenrir Realm and NovelUpdates.

## Features

- 📚 **Add Novels to Watch**: Add multiple novels with their Fenrir Realm and NovelUpdates URLs
- 🔄 **Refresh Chapters**: Automatically crawl and compare chapters from both sources
- 📋 **View Missing Chapters**: See which chapters are available on Fenrir but missing on NovelUpdates
- 📤 **Submit Chapters**: Fill submission forms for missing chapters (preview mode, doesn't auto-submit)

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Environment Variables**:
   ```bash
   set NU_USER=your_username
   set NU_PASS=your_password
   ```

3. **Run the Application**:
   ```bash
   python app.py
   ```

4. **Open in Browser**:
   Navigate to `http://localhost:5000`

## Usage

1. **Add a Novel**:
   - Fill in the novel name
   - Add Fenrir Realm URL (e.g., `https://fenrirealm.com/series/series-name`)
   - Add NovelUpdates URL (e.g., `https://www.novelupdates.com/series/series-name/`)
   - Set the translation group name (default: "Fenrir Realm")
   - Click "Add Novel"

2. **Refresh Chapters**:
   - Click "🔄 Refresh Chapters" on any novel card
   - The app will crawl both sources and compare chapters
   - Progress bar shows the refresh status

3. **View Missing Chapters**:
   - Click "📋 View Missing" to see chapters that exist on Fenrir but not on NovelUpdates
   - Missing chapters are displayed in a modal

4. **Submit Chapters**:
   - After viewing missing chapters, click "📤 Submit All"
   - The app will open a browser and fill submission forms
   - **Note**: Forms are filled but NOT automatically submitted (you review and submit manually)

## Architecture

- **Backend**: Flask web server with SQLite database
- **Frontend**: Modern HTML/CSS/JavaScript with responsive design
- **Crawling**: SeleniumBase for web automation
- **Background Tasks**: Threading for long-running operations

## Files

- `app.py` - Main Flask application and API endpoints
- `templates/index.html` - Frontend HTML
- `static/style.css` - Modern dark theme styling
- `static/app.js` - Frontend JavaScript logic
- `nu_crawler.py` - NovelUpdates crawler module
- `search.py` - Fenrir Realm crawler and submission functions

## Notes

- The submission feature fills forms but does NOT automatically submit them
- To enable auto-submission, uncomment the submit button click in `submit_chapters_task()` function
- The app uses headless mode for refreshing, but opens a visible browser for submissions

"# bot23" 
"# bot23" 
