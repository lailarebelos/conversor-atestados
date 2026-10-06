
# Folhas da marca pulando enquanto o programa abre (gerado por recursos/gerar_imagens.py)
image create photo folha_abertura -data {iVBORw0KGgoAAAANSUhEUgAAABYAAAAdCAIAAAAhEQuvAAABJUlEQVR42mNkMJFgoAwwkaeNR4CRR4ARwmYhVbOaKbOuPbOqGSMDA8OExJ8/vhJtBAc3g649i4k3M78oQpCdi/HH1/+EjZDTZtK1Z9Z1wOllFjzWqpoy24SyIFtLrBHiCowmXixqpkzs3ET5EcUIXQdmUy8WMQXSApgFrtklnoVIa7GnC7L1Q43gF2UkWz/5qXOYGfH3N8VGfPnwnyIjbp/+R6lHTm/7S5ERj679f3SVAlf8/MawrvsX+THy8xvDsoZfP74SUV5gBZcP/Nu78DeyfmKN+PmN4dapf0dW//n4+j8JpRYEvHr4//TWv7dP/0WzmbAREGvPbPvz8sF/0kotIq3FbgRJ1qIBRgYTCWZWBmYWxl/f/5OXzFggGe7v7/9kp3QAi1Fqi6C2uVcAAAAASUVORK5CYII=}
set folhas_x {80 111 141}
set folhas {}
foreach x $folhas_x {
    lappend folhas [.root.canvas create image $x 513 -image folha_abertura -anchor nw]
}
proc pular_folhas {inicio} {
    global folhas folhas_x
    set t [expr {([clock milliseconds] - $inicio) / 1000.0}]
    foreach item $folhas x $folhas_x atraso {0.0 0.2 0.4} {
        set fase [expr {fmod($t - $atraso + 12.0, 1.2) / 1.2}]
        set salto [expr {$fase < 0.5 ? sin($fase * 6.283185307179586) : 0.0}]
        .root.canvas coords $item $x [expr {round(513 - 13.4 * $salto)}]
    }
    after 16 [list pular_folhas $inicio]
}
catch {pular_folhas [clock milliseconds]}
