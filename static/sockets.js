$(document).ready(function(){
    var socket = io.connect('http://localhost:5000/')
    socket.on('connect', function(){
        console.log("User has connected.")
    })

    socket.on('message', function(data){
        if (data.sender == cur_user_id && data.recipient == recip_id || data.sender == recip_id && data.recipient == cur_user_id) {
            if (data.sender == cur_user_id) {
                var sender_name = cur_user_name;
                var sender_photo = cur_user_photo;
                $("#messages").append(
                    "<div class=\"message_container\"><div class=\"sender\"><img class=\"chat_profile\" src=\""+cur_user_photo+"\"><div class=\"message\">"+data.msg+"</div></div></div>"
                )
            }
            else {
                var sender_name = recip_name;
                var sender_photo = recip_photo;
                $("#messages").append(
                    "<div class=\"message_container\"><div class=\"author\">"+ sender_name +"</div><div class=\"message\">"+data.msg_trans+"</div></div>"
                )
            }
            
            console.log('recieved.');
            $(".messages_container").scrollTop($(".messages_container")[0].scrollHeight);
        }

    })
    
    $("#sendButton").on('click', function(){
        var myMessage = $("#myMessage").val()
        console.log(recip_id);
        socket.emit('message', {msg: myMessage, sender: cur_user_id, recipient: recip_id});
        console.log('sent!');
    })
})



function startDictation() {
    if (window.hasOwnProperty('webkitSpeechRecognition')) {
        var recognition = new webkitSpeechRecognition();

        recognition.continuous = true;
        recognition.interimResults = false;

        console.log(user_language);
        recognition.lang = user_language;
        recognition.start();
        document.getElementById('micButton').src = "http://localhost:5000/static/buttons/record_on.svg";

        recognition.onresult = function(e) {
            document.getElementById('myMessage').value = e.results[0][0].transcript;
        };

        recognition.onerror = function(e) {
            recognition.stop();
            document.getElementById('micButton').src = "http://localhost:5000/static/buttons/record_off.svg";
        }

        recognition.onend = function() {
            document.getElementById('micButton').src = "http://localhost:5000/static/buttons/record_off.svg";
        }
    }
}
