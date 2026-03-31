const https = require('https')
const { headers, url } = require('./consts')

const download = (url) => new Promise((resolve, reject) => {
  let options = { headers };
  const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY || process.env.https_proxy || process.env.http_proxy;
  if (proxyUrl) {
    try {
      const { HttpsProxyAgent } = require("https-proxy-agent");
      options.agent = new HttpsProxyAgent(proxyUrl);
    } catch(e) {}
  }
  const req = https.get(url, options, (res) => {
    let data = ''

    res.on('data', (chunk) => {
      data += chunk
    })

    res.on('end', () => {
      resolve(data)
    })
  }).on('error', (err) => {
    reject(err)
  })
})

const formatError = (err) => err.message || err.toString()

module.exports = { download, formatError }
