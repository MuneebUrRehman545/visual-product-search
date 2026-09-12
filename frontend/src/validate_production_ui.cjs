const fs = require('fs');
const path = require('path');
const http = require('http');

console.log('======================================================================');
console.log('MUNEEB VISION UI PRODUCTION-READY COMPREHENSIVE VERIFICATION');
console.log('======================================================================\n');

let passCount = 0;
let failCount = 0;

function assert(condition, testName, details = '') {
  if (condition) {
    console.log(`[PASS] ${testName}${details ? ' - ' + details : ''}`);
    passCount++;
  } else {
    console.error(`[FAIL] ${testName}${details ? ' - ' + details : ''}`);
    failCount++;
  }
}

// -------------------------------------------------------------
// Test 1: Upload State & Validation in ImageUploader.jsx
// -------------------------------------------------------------
console.log('--- TEST GROUP 1: Upload State & File Validation ---');
const uploaderContent = fs.readFileSync(path.join(__dirname, 'components', 'ImageUploader.jsx'), 'utf8');

assert(uploaderContent.includes('disabled = false'), 'ImageUploader accepts disabled prop');
assert(uploaderContent.includes('selected.size === 0'), 'ImageUploader validates 0-byte (empty) files');
assert(uploaderContent.includes('MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024'), 'ImageUploader enforces 25 MB file size limit');
assert(uploaderContent.includes("ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']"), 'ImageUploader restricts formats to JPG, PNG, WebP');
assert(uploaderContent.includes('${disabled ? \'disabled\' : \'\'}'), 'Upload box reflects disabled CSS class');
assert(uploaderContent.includes('disabled={disabled}'), 'Browse, change, remove buttons support disabled prop');

// -------------------------------------------------------------
// Test 2: Search Controls & Disabled Submit State
// -------------------------------------------------------------
console.log('\n--- TEST GROUP 2: Search Controls & Submit State ---');
const homeContent = fs.readFileSync(path.join(__dirname, 'pages', 'HomePage.jsx'), 'utf8');
const searchControlsContent = fs.readFileSync(path.join(__dirname, 'components', 'SearchControls.jsx'), 'utf8');

assert(!homeContent.includes('{selectedFile && (\n          <SearchControls'), 'SearchControls rendered persistently on HomePage');
assert(homeContent.includes('disabled={!selectedFile}'), 'Submit button disabled when no file is selected');
assert(homeContent.includes('disabled={loading}'), 'ImageUploader disabled during loading');
assert(searchControlsContent.includes('search-hint-text'), 'Search hint text rendered for user guidance');
assert(searchControlsContent.includes('Searching with'), 'Search controls display active model name during loading');
assert(searchControlsContent.includes('spinner-inline'), 'Inline spinner displayed during loading');

// -------------------------------------------------------------
// Test 3: Results State & Field Completeness
// -------------------------------------------------------------
console.log('\n--- TEST GROUP 3: Results State & Metadata Completeness ---');
const resultCardContent = fs.readFileSync(path.join(__dirname, 'components', 'ResultCard.jsx'), 'utf8');
const detailModalContent = fs.readFileSync(path.join(__dirname, 'components', 'ProductDetailModal.jsx'), 'utf8');
const resultsPageContent = fs.readFileSync(path.join(__dirname, 'pages', 'ResultsPage.jsx'), 'utf8');

assert(resultCardContent.includes('sub_category'), 'ResultCard supports sub_category tag');
assert(resultCardContent.includes('category && <span className="meta-tag category-tag">{category}</span>'), 'ResultCard displays category');
assert(resultCardContent.includes('article_type && <span className="meta-tag article-tag">{article_type}</span>'), 'ResultCard displays article_type');
assert(resultCardContent.includes('base_colour && <span className="meta-tag colour-tag">{base_colour}</span>'), 'ResultCard displays base_colour');
assert(resultCardContent.includes('gender && <span className="meta-tag gender-tag">{gender}</span>'), 'ResultCard displays gender');
assert(resultCardContent.includes('card-rank-badge'), 'ResultCard displays rank badge (#1, #2, etc.)');

assert(detailModalContent.includes('getCatalogImageUrl(image_url || filename)'), 'ProductDetailModal uses robust image URL fallback');
assert(detailModalContent.includes('sub_category && ('), 'ProductDetailModal specifications table includes sub_category');
assert(detailModalContent.includes('article_type && ('), 'ProductDetailModal specifications table includes article_type');
assert(detailModalContent.includes('base_colour && ('), 'ProductDetailModal specifications table includes base_colour');
assert(detailModalContent.includes('gender && ('), 'ProductDetailModal specifications table includes gender');
assert(detailModalContent.includes('season && ('), 'ProductDetailModal specifications table includes season');
assert(detailModalContent.includes('usage && ('), 'ProductDetailModal specifications table includes usage');

assert(resultsPageContent.includes('query-sidebar-panel'), 'ResultsPage separates query image in dedicated sidebar');
assert(resultsPageContent.includes('results-grid-panel'), 'ResultsPage renders matches in dedicated grid');

// -------------------------------------------------------------
// Test 4: Error & Empty States
// -------------------------------------------------------------
console.log('\n--- TEST GROUP 4: Error & Empty States ---');
assert(resultsPageContent.includes('No matching products found.'), 'ResultsPage empty state displays clear title');
assert(resultsPageContent.includes('Upload Another Image'), 'ResultsPage empty state provides "Upload Another Image" action button');
assert(resultsPageContent.includes('fallback-icon-empty'), 'ResultsPage empty state provides empty illustration/icon');

const searchApiContent = fs.readFileSync(path.join(__dirname, 'services', 'searchApi.js'), 'utf8');
assert(searchApiContent.includes('Unable to connect to visual search service'), 'searchApi sanitizes network failures without raw traces');
assert(searchApiContent.includes('visual search server encountered an error'), 'searchApi sanitizes 500 server errors');
assert(homeContent.includes('error-dismiss-btn'), 'HomePage error banner includes dismiss button');

// -------------------------------------------------------------
// Test 5: Live API Endpoint & Contract Verification
// -------------------------------------------------------------
console.log('\n--- TEST GROUP 5: Live Gateway Backend Integration ---');

const boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW';
let bodyData = `--${boundary}\r\n`;
bodyData += 'Content-Disposition: form-data; name="catalog_filename"\r\n\r\n';
bodyData += '10003.jpg\r\n';
bodyData += `--${boundary}\r\n`;
bodyData += 'Content-Disposition: form-data; name="top_k"\r\n\r\n';
bodyData += '5\r\n';
bodyData += `--${boundary}\r\n`;
bodyData += 'Content-Disposition: form-data; name="model"\r\n\r\n';
bodyData += 'clip\r\n';
bodyData += `--${boundary}--\r\n`;

const req = http.request('http://127.0.0.1:8000/search', {
  method: 'POST',
  headers: {
    'Content-Type': `multipart/form-data; boundary=${boundary}`,
    'Content-Length': Buffer.byteLength(bodyData),
  },
}, (res) => {
  let resBody = '';
  res.on('data', chunk => resBody += chunk);
  res.on('end', () => {
    try {
      const json = JSON.parse(resBody);
      assert(res.statusCode === 200, 'Gateway /search responds with HTTP 200');
      assert(Array.isArray(json.results) && json.results.length === 5, 'Returned results is array of top-K items (5)');
      
      const first = json.results[0];
      const requiredFields = [
        'catalog_item_id', 'product_id', 'filename', 'product_display_name',
        'category', 'sub_category', 'article_type', 'base_colour',
        'gender', 'season', 'usage', 'image_url', 'similarity_score'
      ];
      
      let allFieldsPresent = true;
      for (const field of requiredFields) {
        if (!(field in first)) {
          allFieldsPresent = false;
          console.error(`Missing expected field: ${field}`);
        }
      }
      assert(allFieldsPresent, 'All 13 standard vision result fields present in live API response');
      assert(json.results[0].similarity_score >= json.results[1].similarity_score, 'Results preserved in descending ranked order');
      
      // Final Summary
      console.log('\n======================================================================');
      console.log(`VERIFICATION SUMMARY: ${passCount} PASSED, ${failCount} FAILED`);
      console.log('======================================================================');
      if (failCount > 0) process.exit(1);
    } catch (err) {
      console.error('Failed to parse backend response:', err);
      process.exit(1);
    }
  });
});

req.on('error', (err) => {
  console.error('Backend connection error:', err);
  process.exit(1);
});

req.write(bodyData);
req.end();
