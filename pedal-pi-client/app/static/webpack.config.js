const webpack = require('webpack');
new webpack.DefinePlugin({
  "process.env.NODE_ENV": JSON.stringify("production")
});
const config = {
    entry:  __dirname + '/scripts/index.js',
    output: {
        path: __dirname + '/dist',
        filename: 'bundle.js',
    },
    resolve: {
        extensions: ['.js', '.jsx', '.css']
    },
  
    module: {
        rules: [
            {
            test: /\.(js|jsx)?/,
                exclude: /node_modules/,
                use: 'babel-loader'     
            }        
        ]
    },
    mode: 'development'
};
module.exports = config;
