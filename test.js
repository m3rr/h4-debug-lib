const https = require('https');
const fs = require('fs');

console.log("Hello from test.js");
console.warn("This is a warning");
console.error("This is an error");

https.get('https://example.com', (res) => {
    console.log('HTTP GET statusCode:', res.statusCode);
});

try {
    fs.readFileSync('nonexistent.txt');
} catch (e) {
    console.error("File error caught:", e.message);
}
