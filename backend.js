const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;
const UPLOADS_DIR = path.join(__dirname, 'uploads');

app.use(cors());
app.use(express.json());

// Ensure uploads directory exists
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR);

let filesMeta = []; // For demo: store file meta and comments in-memory

// Helper: Save metadata to disk (not required, but safer for reboot)
function saveMeta() {
  fs.writeFileSync(path.join(UPLOADS_DIR, 'meta.json'), JSON.stringify(filesMeta, null, 2));
}
function loadMeta() {
  try {
    filesMeta = JSON.parse(fs.readFileSync(path.join(UPLOADS_DIR, 'meta.json')));
  } catch {
    filesMeta = [];
  }
}
loadMeta();

// Multer setup
const storage = multer.diskStorage({
  destination: UPLOADS_DIR,
  filename: (req, file, cb) => {
    const unique = Date.now() + '-' + Math.round(Math.random()*1e9);
    cb(null, unique + '-' + file.originalname);
  }
});
const upload = multer({ storage, limits: { fileSize: 10*1024*1024 } });

// Upload endpoint
app.post('/upload', upload.single('file'), (req, res) => {
  if (!req.file || !req.body.uploader) return res.status(400).json({ error: 'Missing file or uploader name' });

  const meta = {
    id: req.file.filename, // unique id
    originalname: req.file.originalname,
    uploader: req.body.uploader,
    uploadDate: new Date().toISOString(),
    downloads: 0,
    comments: []
  };
  filesMeta.unshift(meta);
  saveMeta();
  res.json({ success: true, file: meta });
});

// List files endpoint
app.get('/files', (req, res) => {
  res.json(filesMeta);
});

// Download endpoint (+counts)
app.get('/download/:id', (req, res) => {
  const meta = filesMeta.find(f => f.id === req.params.id);
  if (!meta) return res.status(404).json({ error: 'Not found' });

  const filepath = path.join(UPLOADS_DIR, req.params.id);
  if (!fs.existsSync(filepath)) return res.status(404).json({ error: 'File missing' });

  meta.downloads = (meta.downloads||0) + 1;
  saveMeta();
  res.download(filepath, meta.originalname);
});

// Post a comment
app.post('/comment/:id', (req, res) => {
  const { name, text } = req.body;
  const meta = filesMeta.find(f => f.id === req.params.id);
  if (!meta || !name || !text) return res.status(400).json({ error: 'Bad request' });

  meta.comments = meta.comments || [];
  meta.comments.push({ name, text, date: new Date().toISOString() });
  saveMeta();
  res.json({ success: true, comments: meta.comments });
});

// Admin dashboard: simple example endpoint (protected)
app.post('/admin', (req, res) => {
  const { password } = req.body;
  if (password !== process.env.ADMIN_PASSWORD)
    return res.status(401).json({ error: 'Unauthorized' });
  res.json({ files: filesMeta });
});

// Serve uploaded files (optional direct access)
app.use('/uploads', express.static(UPLOADS_DIR));

// Basic root endpoint
app.get('/', (req, res) => {
  res.send('ShareLit backend is running!');
});

app.listen(PORT, () => {
  console.log('Server running on', PORT);
});

